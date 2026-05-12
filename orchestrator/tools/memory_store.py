from __future__ import annotations
"""
memory_store.py — Persistent vector memory for Agent-Q3.

Architecture:
  - Short-term:  Redis (TTL 24h) — fast recent context
  - Long-term:   Postgres + pgvector (384-dim embeddings via nomic-embed-text)
  - Episodic:    Structured JSON records (user prefs, project facts, corrections)

Usage:
  from orchestrator.tools.memory_store import MemoryStore
  mem = MemoryStore()
  await mem.save(text="Nick prefers Q4_K_M quants", tags=["preference","models"])
  results = await mem.search("model preferences", k=5)
"""
import hashlib
import json
import time
from typing import Optional
import httpx

from orchestrator.config import settings


class MemoryStore:
    def __init__(self):
        self.ollama_url = settings.ollama_base_url
        self.embed_model = "nomic-embed-text"
        self.db_url = getattr(settings, "database_url", None)
        self.redis_url = getattr(settings, "redis_url", None)
        self._pg_ready = False
        self._redis_ready = False

    async def _embed(self, text: str) -> list[float]:
        """Generate 384-dim embedding via Ollama nomic-embed-text."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text}
            )
            return r.json()["embedding"]

    async def save(
        self,
        text: str,
        tags: list[str] | None = None,
        source: str = "agent",
        session_id: str | None = None,
    ) -> str:
        """Save a memory entry. Returns memory ID."""
        mem_id = hashlib.sha256(f"{text}{time.time()}".encode()).hexdigest()[:16]
        embedding = await self._embed(text)
        record = {
            "id": mem_id,
            "text": text,
            "tags": tags or [],
            "source": source,
            "session_id": session_id,
            "timestamp": int(time.time()),
            "embedding": embedding,
        }
        await self._save_postgres(record)
        await self._save_redis(mem_id, record)
        return mem_id

    async def search(
        self,
        query: str,
        k: int = 5,
        tags: list[str] | None = None,
        min_score: float = 0.7,
    ) -> list[dict]:
        """Semantic search over long-term memory."""
        embedding = await self._embed(query)
        return await self._search_postgres(embedding, k=k, tags=tags, min_score=min_score)

    async def get_recent(self, n: int = 10) -> list[dict]:
        """Get n most recent memories from Redis (fast path)."""
        return await self._get_redis_recent(n)

    async def get_episodic(self, category: str) -> list[dict]:
        """Get structured episodic memories by category (preferences, corrections, facts)."""
        return await self._search_postgres_by_tag(category)

    # -- Postgres backend ----------------------------------------------------
    async def _save_postgres(self, record: dict):
        if not self.db_url:
            return
        try:
            import asyncpg
            conn = await asyncpg.connect(self.db_url)
            await conn.execute(
                """INSERT INTO agent_memory
                   (id, text, tags, source, session_id, timestamp, embedding)
                   VALUES ($1,$2,$3,$4,$5,to_timestamp($6),$7)
                   ON CONFLICT (id) DO NOTHING""",
                record["id"],
                record["text"],
                record["tags"],
                record["source"],
                record["session_id"],
                record["timestamp"],
                json.dumps(record["embedding"]),
            )
            await conn.close()
        except Exception as e:
            pass  # Degrade gracefully if DB unavailable

    async def _search_postgres(
        self, embedding: list[float], k: int, tags: list[str] | None, min_score: float
    ) -> list[dict]:
        if not self.db_url:
            return []
        try:
            import asyncpg
            conn = await asyncpg.connect(self.db_url)
            vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
            rows = await conn.fetch(
                """SELECT id, text, tags, source, session_id,
                          1 - (embedding <=> $1::vector) as score
                   FROM agent_memory
                   WHERE 1 - (embedding <=> $1::vector) >= $2
                   ORDER BY embedding <=> $1::vector
                   LIMIT $3""",
                vec_str, min_score, k
            )
            await conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    async def _search_postgres_by_tag(self, tag: str) -> list[dict]:
        if not self.db_url:
            return []
        try:
            import asyncpg
            conn = await asyncpg.connect(self.db_url)
            rows = await conn.fetch(
                "SELECT id, text, tags, source, timestamp FROM agent_memory WHERE $1=ANY(tags) ORDER BY timestamp DESC LIMIT 50",
                tag
            )
            await conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # -- Redis backend -------------------------------------------------------
    async def _save_redis(self, mem_id: str, record: dict):
        if not self.redis_url:
            return
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(self.redis_url)
            await r.setex(f"mem:{mem_id}", 86400, json.dumps({
                k: v for k, v in record.items() if k != "embedding"
            }))
            await r.lpush("mem:recent", mem_id)
            await r.ltrim("mem:recent", 0, 99)
            await r.aclose()
        except Exception:
            pass

    async def _get_redis_recent(self, n: int) -> list[dict]:
        if not self.redis_url:
            return []
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(self.redis_url)
            ids = await r.lrange("mem:recent", 0, n - 1)
            results = []
            for mid in ids:
                raw = await r.get(f"mem:{mid.decode()}")
                if raw:
                    results.append(json.loads(raw))
            await r.aclose()
            return results
        except Exception:
            return []


# -- Migration SQL (run once on Postgres) -----------------------------------
MEMORY_MIGRATION_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS agent_memory (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    tags        TEXT[] DEFAULT '{}',
    source      TEXT DEFAULT 'agent',
    session_id  TEXT,
    timestamp   TIMESTAMPTZ DEFAULT NOW(),
    embedding   vector(384)
);

CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx
    ON agent_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS agent_memory_tags_idx
    ON agent_memory USING GIN (tags);
""";
