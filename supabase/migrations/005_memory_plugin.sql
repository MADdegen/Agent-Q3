-- Migration 005: Agent-Q3 Memory Plugin
-- Run on Railway Postgres (already has pgvector from 003)
-- Adds episodic memory table + memory_skills view

CREATE EXTENSION IF NOT EXISTS vector;

-- Core memory table (embeddings from nomic-embed-text, 384-dim)
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

-- Episodic memory: structured facts, corrections, preferences
CREATE TABLE IF NOT EXISTS episodic_memory (
    id          SERIAL PRIMARY KEY,
    category    TEXT NOT NULL,  -- 'preference' | 'correction' | 'fact' | 'project'
    key         TEXT NOT NULL,
    value       JSONB NOT NULL,
    confidence  FLOAT DEFAULT 1.0,
    source      TEXT DEFAULT 'agent',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(category, key)
);

CREATE INDEX IF NOT EXISTS episodic_memory_category_idx ON episodic_memory(category);

-- Memory skill invocations log
CREATE TABLE IF NOT EXISTS memory_skill_log (
    id          SERIAL PRIMARY KEY,
    skill       TEXT NOT NULL,
    query       TEXT,
    result_ids  TEXT[],
    model_used  TEXT,
    latency_ms  INT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- View: recent memories with score placeholder for API
CREATE OR REPLACE VIEW recent_memories AS
SELECT id, text, tags, source, session_id, timestamp, NULL::FLOAT as score
FROM agent_memory
ORDER BY timestamp DESC
LIMIT 100;
