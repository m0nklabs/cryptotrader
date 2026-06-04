-- Multi-Brain AI tables
-- Depends on: db/schema.sql (core tables)

-- ---------------------------------------------------------------------------
-- System prompts — versioned prompt storage per role
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_prompts (
    id              TEXT        PRIMARY KEY,            -- e.g. "tactical_v1"
    role            TEXT        NOT NULL,               -- screener|tactical|fundamental|strategist
    version         INTEGER     NOT NULL DEFAULT 1,
    content         TEXT        NOT NULL,
    description     TEXT        NOT NULL DEFAULT '',
    is_active       BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (role, version)
);

CREATE INDEX IF NOT EXISTS idx_system_prompts_role ON system_prompts (role, is_active);

-- ---------------------------------------------------------------------------
-- Role configurations — provider/model assignment per role
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_role_configs (
    name                TEXT        PRIMARY KEY,         -- screener|tactical|fundamental|strategist
    provider            TEXT        NOT NULL,            -- deepseek|openai|xai|ollama|google
    model               TEXT        NOT NULL,
    system_prompt_id    TEXT        REFERENCES system_prompts(id),
    temperature         REAL        NOT NULL DEFAULT 0.0,
    max_tokens          INTEGER     NOT NULL DEFAULT 4096,
    weight              REAL        NOT NULL DEFAULT 1.0,
    enabled             BOOLEAN     NOT NULL DEFAULT true,
    fallback_provider   TEXT,
    fallback_model      TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- AI usage log — cost/token tracking per request
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_usage_log (
    id              BIGSERIAL   PRIMARY KEY,
    role            TEXT        NOT NULL,
    provider        TEXT        NOT NULL,
    model           TEXT        NOT NULL,
    tokens_in       INTEGER     NOT NULL DEFAULT 0,
    tokens_out      INTEGER     NOT NULL DEFAULT 0,
    cost_usd        REAL        NOT NULL DEFAULT 0.0,
    latency_ms      REAL        NOT NULL DEFAULT 0.0,
    symbol          TEXT        NOT NULL DEFAULT '',
    success         BOOLEAN     NOT NULL DEFAULT true,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_log_created ON ai_usage_log (created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_role    ON ai_usage_log (role);
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_symbol  ON ai_usage_log (symbol);

-- ---------------------------------------------------------------------------
-- AI decisions — consensus decisions audit trail
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_decisions (
    id                  BIGSERIAL   PRIMARY KEY,
    symbol              TEXT        NOT NULL,
    timeframe           TEXT        NOT NULL,
    final_action        TEXT        NOT NULL,            -- BUY|SELL|NEUTRAL|VETO
    final_confidence    REAL        NOT NULL DEFAULT 0.0,
    verdicts            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    reasoning           TEXT        NOT NULL DEFAULT '',
    vetoed_by           TEXT,
    total_cost_usd      REAL        NOT NULL DEFAULT 0.0,
    total_latency_ms    REAL        NOT NULL DEFAULT 0.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_decisions_symbol  ON ai_decisions (symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_action  ON ai_decisions (final_action);
