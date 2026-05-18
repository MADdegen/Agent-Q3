"""
Agent-Q3 — Redis-backed shared memory layer.

Used by all services (multimodal, coder, research, monitor) to:
- Cache MCP tool call results (TTL'd)
- Store conversation history per session
- Persist monitor metrics across restarts
- Track skill activation log
- Coordinate cross-service rate limits

Falls back to a no-op in-memory store if REDIS_URL is unset.
"""

import json
import time
from typing import Any, Optional

import structlog

from .config import settings

log = structlog.get_logger(__name__)


class _InMemoryFallback:
    """Drop-in async stub used when REDIS_URL is unset."""
    def __init__(self):
        self._store: dict[str, tuple[float, str]] = {}
        self._lists: dict[str, list] = {}

    async def get(self, key: str) -> Optional[str]:
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at and time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        exp = (time.time() + ex) if ex else 0
        self._store[key] = (exp, value)

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    async def lpush(self, key: str, *values: str) -> int:
        self._lists.setdefault(key, [])
        for v in values:
            self._lists[key].insert(0, v)
        return len(self._lists[key])

    async def lrange(self, key: str, start: int, stop: int) -> list:
        lst = self._lists.get(key, [])
        if stop == -1:
            return lst[start:]
        return lst[start:stop + 1]

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        lst = self._lists.get(key, [])
        if stop == -1:
            self._lists[key] = lst[start:]
        else:
            self._lists[key] = lst[start:stop + 1]

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class Memory:
    """Async memory facade. Uses redis.asyncio when REDIS_URL set, else in-memory."""

    def __init__(self):
        self._client = None
        self._backend: str = "uninitialized"

    async def connect(self) -> None:
        if settings.redis_url:
            try:
                from redis.asyncio import from_url
                self._client = from_url(settings.redis_url, decode_responses=True)
                await self._client.ping()
                self._backend = "redis"
                log.info("memory connected", backend="redis", url=settings.redis_url.split("@")[-1])
                return
            except Exception as e:
                log.warning("redis unavailable, falling back to in-memory", error=str(e))
        self._client = _InMemoryFallback()
        self._backend = "in-memory"
        log.info("memory connected", backend="in-memory")

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def client(self):
        return self._client

    # ── Typed helpers ────────────────────────────────────────────────────────

    async def cache_get(self, key: str) -> Optional[Any]:
        raw = await self._client.get(f"cache:{key}")
        return json.loads(raw) if raw else None

    async def cache_set(self, key: str, value: Any, ttl_secs: int = 300) -> None:
        await self._client.set(f"cache:{key}", json.dumps(value), ex=ttl_secs)

    async def log_event(self, channel: str, event: dict, max_history: int = 500) -> None:
        key = f"events:{channel}"
        await self._client.lpush(key, json.dumps({"ts": time.time(), **event}))
        await self._client.ltrim(key, 0, max_history - 1)

    async def get_events(self, channel: str, limit: int = 50) -> list[dict]:
        raw_items = await self._client.lrange(f"events:{channel}", 0, limit - 1)
        return [json.loads(x) for x in raw_items]

    async def session_append(self, session_id: str, message: dict, max_turns: int = 50) -> None:
        key = f"session:{session_id}"
        await self._client.lpush(key, json.dumps(message))
        await self._client.ltrim(key, 0, max_turns - 1)

    async def session_history(self, session_id: str, limit: int = 50) -> list[dict]:
        raw_items = await self._client.lrange(f"session:{session_id}", 0, limit - 1)
        return [json.loads(x) for x in reversed(raw_items)]

    async def ping(self) -> bool:
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def close(self) -> None:
        try:
            await self._client.close()
        except Exception:
            pass


memory = Memory()
