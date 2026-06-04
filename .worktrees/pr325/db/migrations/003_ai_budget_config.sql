-- AI Budget Configuration
-- Adds budget guardrails for LLM spend control

-- ---------------------------------------------------------------------------
-- Budget configuration — global and per-role spend limits
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_budget_config (
    id                  TEXT        PRIMARY KEY,            -- 'global' or role name (screener|tactical|fundamental|strategist)
    daily_limit_usd     REAL        NOT NULL DEFAULT 0.0,   -- 0.0 = unlimited
    monthly_limit_usd   REAL        NOT NULL DEFAULT 0.0,   -- 0.0 = unlimited
    enabled             BOOLEAN     NOT NULL DEFAULT true,  -- false = budgets disabled for this scope
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert default global budget config (unlimited by default)
INSERT INTO ai_budget_config (id, daily_limit_usd, monthly_limit_usd, enabled)
VALUES ('global', 0.0, 0.0, true)
ON CONFLICT (id) DO NOTHING;

-- Insert default per-role budget configs (inherit from global by default, i.e., unlimited)
INSERT INTO ai_budget_config (id, daily_limit_usd, monthly_limit_usd, enabled)
VALUES
    ('screener', 0.0, 0.0, true),
    ('tactical', 0.0, 0.0, true),
    ('fundamental', 0.0, 0.0, true),
    ('strategist', 0.0, 0.0, true)
ON CONFLICT (id) DO NOTHING;
