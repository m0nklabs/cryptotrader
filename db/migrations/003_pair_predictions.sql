-- PairDossier multi-agent prediction timeline
-- Issue #231: per-pair prediction history with outcome tracking + model rankings
-- Depends on: 002_coin_dossier.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- pair_predictions — append-only prediction per pair per role per call
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pair_predictions (
    id              BIGSERIAL       PRIMARY KEY,
    exchange        TEXT            NOT NULL,
    symbol          TEXT            NOT NULL,
    role            TEXT            NOT NULL,           -- screener|tactical|fundamental|strategist
    action          TEXT            NOT NULL,           -- BUY|SELL|NEUTRAL|VETO
    confidence      DOUBLE PRECISION NOT NULL DEFAULT 0.0,  -- 0.0–1.0
    reasoning       TEXT            NOT NULL DEFAULT '',
    horizon         TEXT            NOT NULL DEFAULT '24h',  -- prediction horizon

    -- Model metadata
    provider        TEXT            NOT NULL DEFAULT '',
    model           TEXT            NOT NULL DEFAULT '',
    tokens_in       INTEGER         NOT NULL DEFAULT 0,
    tokens_out      INTEGER         NOT NULL DEFAULT 0,
    latency_ms      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0.0,

    -- Outcome tracking (filled in after horizon elapses)
    outcome_correct BOOLEAN,                            -- NULL = pending
    price_at_prediction DOUBLE PRECISION,
    price_at_outcome    DOUBLE PRECISION,
    outcome_evaluated_at TIMESTAMPTZ,

    -- Consensus linkage (optional — set when part of a consensus run)
    consensus_id    BIGINT          REFERENCES ai_decisions(id) ON DELETE SET NULL,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pair_pred_symbol_role
    ON pair_predictions (exchange, symbol, role, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pair_pred_symbol_time
    ON pair_predictions (exchange, symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pair_pred_outcome
    ON pair_predictions (outcome_correct, created_at DESC)
    WHERE outcome_correct IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pair_pred_model
    ON pair_predictions (model, created_at DESC);

-- ---------------------------------------------------------------------------
-- prediction_cache — 5-minute TTL cache to avoid re-running same pair
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prediction_cache (
    id              BIGSERIAL       PRIMARY KEY,
    cache_key       TEXT            NOT NULL UNIQUE,    -- e.g. "bitfinex:BTCUSD:1h"
    predictions     JSONB           NOT NULL DEFAULT '[]'::jsonb,
    consensus_action TEXT           NOT NULL DEFAULT 'NEUTRAL',
    consensus_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    expires_at      TIMESTAMPTZ     NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pred_cache_key ON prediction_cache (cache_key, expires_at);

COMMIT;
