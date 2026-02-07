-- Coin Dossier tables
-- Depends on: db/schema.sql (core tables)
--
-- A daily "dossier" per coin/pair: LLM-generated technical analysis that
-- references prior entries, explains past price action, and leaves a new
-- prediction.  Designed to accumulate a coherent narrative over time.

BEGIN;

-- ---------------------------------------------------------------------------
-- coin_dossier_entries — one row per coin per day
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coin_dossier_entries (
    id              BIGSERIAL       PRIMARY KEY,
    exchange        TEXT            NOT NULL,
    symbol          TEXT            NOT NULL,
    entry_date      DATE            NOT NULL DEFAULT CURRENT_DATE,

    -- Stats snapshot at time of analysis
    price           DOUBLE PRECISION,
    change_24h      DOUBLE PRECISION,           -- percentage
    change_7d       DOUBLE PRECISION,           -- percentage
    volume_24h      DOUBLE PRECISION,
    rsi             DOUBLE PRECISION,
    macd_signal     TEXT,                        -- 'bullish' | 'bearish' | 'neutral'
    ema_trend       TEXT,                        -- 'up' | 'down' | 'flat'
    support_level   DOUBLE PRECISION,
    resistance_level DOUBLE PRECISION,
    signal_score    DOUBLE PRECISION,            -- composite signal score (-100..100)

    -- LLM-generated narrative
    lore            TEXT            NOT NULL DEFAULT '',  -- background/history of the coin
    stats_summary   TEXT            NOT NULL DEFAULT '',  -- human-readable stats recap
    tech_analysis   TEXT            NOT NULL DEFAULT '',  -- detailed technical analysis
    retrospective   TEXT            NOT NULL DEFAULT '',  -- review of previous prediction
    prediction      TEXT            NOT NULL DEFAULT '',  -- new expectation / outlook
    full_narrative  TEXT            NOT NULL DEFAULT '',  -- complete combined narrative

    -- Prediction tracking
    predicted_direction TEXT,                    -- 'up' | 'down' | 'sideways'
    predicted_target    DOUBLE PRECISION,        -- price target
    predicted_timeframe TEXT DEFAULT '24h',      -- prediction horizon
    prediction_correct  BOOLEAN,                -- filled in next day retrospective

    -- Metadata
    model_used      TEXT            NOT NULL DEFAULT '',
    tokens_used     INTEGER         NOT NULL DEFAULT 0,
    generation_time_ms INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    UNIQUE (exchange, symbol, entry_date)
);

CREATE INDEX IF NOT EXISTS idx_dossier_symbol_date
    ON coin_dossier_entries (exchange, symbol, entry_date DESC);

CREATE INDEX IF NOT EXISTS idx_dossier_date
    ON coin_dossier_entries (entry_date DESC);

-- ---------------------------------------------------------------------------
-- coin_profiles — static/semi-static coin info (lore building blocks)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coin_profiles (
    id              SERIAL          PRIMARY KEY,
    symbol          TEXT            NOT NULL UNIQUE,
    name            TEXT            NOT NULL DEFAULT '',
    description     TEXT            NOT NULL DEFAULT '',
    category        TEXT            NOT NULL DEFAULT '',  -- 'L1', 'DeFi', 'Meme', etc.
    founded_year    INTEGER,
    notable_events  JSONB           NOT NULL DEFAULT '[]'::jsonb,  -- [{date, event}]
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMIT;
