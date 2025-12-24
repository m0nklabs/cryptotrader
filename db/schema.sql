-- cryptotrader v2 - database schema (skeleton)
--
-- Notes:
-- - This file is intentionally minimal and idempotent.
-- - PostgreSQL recommended.
-- - Tables here back the optional persistence layer and indicator config.

BEGIN;

-- =====================
-- Reference / metadata
-- =====================

CREATE TABLE IF NOT EXISTS exchanges (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS symbols (
    id SERIAL PRIMARY KEY,
    exchange_code VARCHAR(50),
    symbol VARCHAR(50) NOT NULL,
    base_asset VARCHAR(50),
    quote_asset VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_symbols_exchange_symbol UNIQUE (exchange_code, symbol)
);

CREATE INDEX IF NOT EXISTS idx_symbols_symbol
    ON symbols(symbol);

CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===============
-- Candles (OHLCV)
-- ===============

CREATE TABLE IF NOT EXISTS candles (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open_time TIMESTAMP NOT NULL,
    close_time TIMESTAMP NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(30, 8) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_candles_exchange_symbol_tf_open_time UNIQUE (exchange, symbol, timeframe, open_time)
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_time
    ON candles(symbol, timeframe, open_time DESC);

CREATE INDEX IF NOT EXISTS idx_candles_lookup
    ON candles(exchange, symbol, timeframe, open_time);


-- ==================================
-- Market data ingestion job tracking
-- ==================================

CREATE TABLE IF NOT EXISTS market_data_jobs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    job_type VARCHAR(20) NOT NULL, -- backfill | realtime | repair
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_market_data_jobs_lookup
    ON market_data_jobs(exchange, symbol, timeframe, created_at DESC);

CREATE TABLE IF NOT EXISTS market_data_job_runs (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES market_data_jobs(id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    candles_fetched INTEGER DEFAULT 0,
    candles_upserted INTEGER DEFAULT 0,
    last_open_time TIMESTAMP,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_market_data_job_runs_job
    ON market_data_job_runs(job_id, started_at DESC);


-- ======================
-- Data quality (gap log)
-- ======================

CREATE TABLE IF NOT EXISTS candle_gaps (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    expected_open_time TIMESTAMP NOT NULL,
    expected_close_time TIMESTAMP,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    repaired_at TIMESTAMP,
    notes TEXT,
    CONSTRAINT uq_candle_gaps UNIQUE (exchange, symbol, timeframe, expected_open_time)
);

CREATE INDEX IF NOT EXISTS idx_candle_gaps_lookup
    ON candle_gaps(exchange, symbol, timeframe, detected_at DESC);


-- ======================================
-- Indicator configuration (optional, DB)
-- ======================================

CREATE TABLE IF NOT EXISTS indicators (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    indicator_type VARCHAR(50) NOT NULL,
    description TEXT,
    default_weight DECIMAL(3,2) DEFAULT 0.15,
    min_weight DECIMAL(3,2) DEFAULT 0.00,
    max_weight DECIMAL(3,2) DEFAULT 1.00,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS indicator_weights (
    id SERIAL PRIMARY KEY,
    indicator_id INTEGER NOT NULL REFERENCES indicators(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    weight DECIMAL(3,2) NOT NULL,
    strategy VARCHAR(50) DEFAULT 'default',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_indicator_weights UNIQUE (indicator_id, user_id, strategy)
);

-- Legacy-style logging uses coin_id. If/when v2 moves to symbol-based logging,
-- replace coin_id with symbol and update the query in shared/indicator_config.py.
CREATE TABLE IF NOT EXISTS indicator_signals (
    id SERIAL PRIMARY KEY,
    indicator_id INTEGER NOT NULL REFERENCES indicators(id) ON DELETE CASCADE,
    coin_id INTEGER,
    timeframe VARCHAR(10) NOT NULL,
    signal VARCHAR(10) NOT NULL,
    strength INTEGER CHECK (strength >= 0 AND strength <= 100),
    value DECIMAL(20,8),
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_indicator_signals_lookup
    ON indicator_signals(indicator_id, coin_id, timeframe, timestamp);


-- =======================
-- Portfolio / risk basics
-- =======================

CREATE TABLE IF NOT EXISTS wallet_snapshots (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exchange VARCHAR(50) NOT NULL,
    wallet_type VARCHAR(50),
    currency VARCHAR(20) NOT NULL,
    balance DECIMAL(30, 10) NOT NULL,
    available_balance DECIMAL(30, 10),
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_wallet_snapshots_lookup
    ON wallet_snapshots(exchange, currency, created_at DESC);

CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL, -- long | short
    amount DECIMAL(30, 10) NOT NULL,
    entry_price DECIMAL(30, 10),
    mark_price DECIMAL(30, 10),
    unrealized_pnl DECIMAL(30, 10),
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_positions_lookup
    ON positions(exchange, symbol, created_at DESC);


-- =====================
-- Orders & trade fills
-- =====================

CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    order_id TEXT,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    amount DECIMAL(30, 10) NOT NULL,
    price DECIMAL(30, 10),
    status VARCHAR(30),
    raw_json TEXT,
    CONSTRAINT uq_orders_exchange_order_id UNIQUE (exchange, order_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_lookup
    ON orders(exchange, symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS trade_fills (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    order_id TEXT,
    trade_id TEXT,
    side VARCHAR(10) NOT NULL,
    amount DECIMAL(30, 10) NOT NULL,
    price DECIMAL(30, 10) NOT NULL,
    fee_currency VARCHAR(20),
    fee_amount DECIMAL(30, 10),
    raw_json TEXT,
    CONSTRAINT uq_trade_fills_exchange_trade_id UNIQUE (exchange, trade_id)
);

CREATE INDEX IF NOT EXISTS idx_trade_fills_lookup
    ON trade_fills(exchange, symbol, created_at DESC);


-- ==================
-- Fee schedule (opt)
-- ==================

CREATE TABLE IF NOT EXISTS fee_schedules (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50),
    maker_fee_rate DECIMAL(18, 10),
    taker_fee_rate DECIMAL(18, 10),
    assumed_spread_bps INTEGER,
    assumed_slippage_bps INTEGER,
    notes TEXT,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_fee_schedules_lookup
    ON fee_schedules(exchange, symbol, created_at DESC);


-- =============================
-- Opportunities (score snapshots)
-- =============================

CREATE TABLE IF NOT EXISTS opportunities (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(50),
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    side VARCHAR(10) NOT NULL,
    -- JSON-encoded indicator signals and explanations (kept as TEXT for portability)
    signals_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_opportunities_symbol_tf_time
    ON opportunities(symbol, timeframe, created_at DESC);


-- =====================
-- Execution (audit trail)
-- =====================

CREATE TABLE IF NOT EXISTS execution_intents (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    amount DECIMAL(30, 8) NOT NULL,
    order_type VARCHAR(20) NOT NULL DEFAULT 'market',
    limit_price DECIMAL(30, 8),
    metadata_json TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'created'
);

CREATE INDEX IF NOT EXISTS idx_execution_intents_exchange_time
    ON execution_intents(exchange, created_at DESC);

CREATE TABLE IF NOT EXISTS execution_results (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    intent_id BIGINT REFERENCES execution_intents(id) ON DELETE SET NULL,
    dry_run BOOLEAN NOT NULL,
    accepted BOOLEAN NOT NULL,
    reason TEXT NOT NULL,
    order_id TEXT,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_execution_results_intent
    ON execution_results(intent_id);


-- ===========
-- Audit events
-- ===========

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    context_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_events_time
    ON audit_events(event_time DESC);


-- ================
-- Automation rules
-- ================

CREATE TABLE IF NOT EXISTS automation_rules (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50),  -- NULL = global
    rule_type VARCHAR(50) NOT NULL,
    value JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_rules_symbol
    ON automation_rules(symbol, rule_type, is_active);


-- ============================
-- Paper trading (simulation)
-- ============================

CREATE TABLE IF NOT EXISTS paper_orders (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY/SELL
    order_type VARCHAR(20) NOT NULL,  -- MARKET/LIMIT
    qty DECIMAL(20,8) NOT NULL,
    limit_price DECIMAL(20,8),
    status VARCHAR(20) NOT NULL,  -- PENDING/FILLED/CANCELLED
    fill_price DECIMAL(20,8),
    slippage_bps DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol_status
    ON paper_orders(symbol, status, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) UNIQUE NOT NULL,
    qty DECIMAL(20,8) NOT NULL,
    avg_entry DECIMAL(20,8) NOT NULL,
    realized_pnl DECIMAL(20,8) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_symbol
    ON paper_positions(symbol);

COMMIT;
