-- ── Enterprise Agentic AI Platform — Database Schema ────────────────────────
-- Run via Alembic migrations in production; this file seeds local Docker init.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- fast text search

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      VARCHAR(64) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(32) NOT NULL DEFAULT 'user',   -- user | admin | analyst
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Sessions ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_key VARCHAR(128) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX ON sessions(user_id);
CREATE INDEX ON sessions(expires_at);

-- ── Interaction History ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS interaction_history (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id       UUID,
    task             TEXT NOT NULL,
    response_summary TEXT,
    task_type        VARCHAR(64),
    agent_path       TEXT[],          -- ordered list of agents invoked
    iterations       INTEGER,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    latency_ms       INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON interaction_history(user_id, created_at DESC);

-- ── User Long-term Memory ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_memories (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fact        TEXT NOT NULL,
    category    VARCHAR(64) NOT NULL DEFAULT 'general',
    confidence  FLOAT NOT NULL DEFAULT 1.0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, fact)
);

CREATE INDEX ON user_memories(user_id, category);

-- ── Workflow Definitions ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workflows (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(128) NOT NULL,
    description TEXT,
    definition  JSONB NOT NULL,       -- LangGraph state graph config
    created_by  UUID REFERENCES users(id),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Workflow Runs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workflow_runs (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id  UUID NOT NULL REFERENCES workflows(id),
    user_id      UUID NOT NULL REFERENCES users(id),
    status       VARCHAR(32) NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed
    input        JSONB NOT NULL DEFAULT '{}',
    output       JSONB,
    error        TEXT,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON workflow_runs(user_id, created_at DESC);
CREATE INDEX ON workflow_runs(status) WHERE status IN ('pending', 'running');

-- ── Audit Log ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL PRIMARY KEY,
    user_id    UUID REFERENCES users(id),
    action     VARCHAR(128) NOT NULL,
    resource   VARCHAR(128),
    details    JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON audit_log(user_id, created_at DESC);
CREATE INDEX ON audit_log(action);
