-- Migration 005: Portfolio tracking tables
--
-- Creates tables for:
-- - Portfolio snapshots (equity curve, performance metrics)
-- - Position history (audit trail of position changes)
-- - Balance snapshots (cash balances over time)
--
-- Run after: 001_ai_tables.sql, 002_coin_dossier.sql, 003_ai_budget_config.sql, 004_notification_tables.sql

BEGIN;

-- Portfolio snapshots for equity curve tracking
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    total_equity DECIMAL(20, 8) NOT NULL,
    cash_balance DECIMAL(20, 8) NOT NULL,
    position_value DECIMAL(20, 8) NOT NULL,
    unrealized_pnl DECIMAL(20, 8) NOT NULL,
    realized_pnl DECIMAL(20, 8) NOT NULL,
    total_pnl DECIMAL(20, 8) NOT NULL,
    quote_currency VARCHAR(10) DEFAULT 'USDT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_timestamp
    ON portfolio_snapshots(timestamp DESC);

-- Position history for audit trail
CREATE TABLE IF NOT EXISTS position_history (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    avg_entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8) NOT NULL,
    unrealized_pnl DECIMAL(20, 8) NOT NULL,
    realized_pnl DECIMAL(20, 8) NOT NULL,
    cost_basis VARCHAR(20) DEFAULT 'FIFO', -- FIFO, LIFO, or average
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_position_history_symbol_timestamp
    ON position_history(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_position_history_timestamp
    ON position_history(timestamp DESC);

-- Balance snapshots for tracking cash over time
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    available DECIMAL(20, 8) NOT NULL,
    reserved DECIMAL(20, 8) NOT NULL,
    total DECIMAL(20, 8) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_balance_snapshots_timestamp
    ON balance_snapshots(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_balance_snapshots_exchange_currency
    ON balance_snapshots(exchange, currency, timestamp DESC);

COMMIT;
