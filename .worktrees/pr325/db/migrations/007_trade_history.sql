-- Migration 007: Trade history and audit logging
--
-- Creates tables for:
-- - Trade executions (filled orders with full details)
-- - Order audit log (all order state changes)
--
-- Run after: 006_watchlists.sql

BEGIN;

-- Trade executions (completed fills)
CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    trade_id VARCHAR(100) UNIQUE NOT NULL,
    order_id VARCHAR(100),
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL, -- BUY or SELL
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    fee_currency VARCHAR(10),
    quote_qty DECIMAL(20, 8) NOT NULL, -- quantity * price
    trade_type VARCHAR(20) DEFAULT 'market', -- market, limit, stop
    execution_time TIMESTAMP NOT NULL,
    is_paper BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time
    ON trades(symbol, execution_time DESC);

CREATE INDEX IF NOT EXISTS idx_trades_execution_time
    ON trades(execution_time DESC);

CREATE INDEX IF NOT EXISTS idx_trades_order_id
    ON trades(order_id);

-- Order audit log (all order state changes)
CREATE TABLE IF NOT EXISTS order_audit_log (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    quantity DECIMAL(20, 8),
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    limit_price DECIMAL(20, 8),
    stop_price DECIMAL(20, 8),
    avg_fill_price DECIMAL(20, 8),
    event_type VARCHAR(20) NOT NULL, -- CREATED, FILLED, PARTIAL_FILL, CANCELLED, REJECTED
    event_time TIMESTAMP NOT NULL,
    metadata JSONB, -- Additional context (strategy, reason, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_order_audit_log_order_id
    ON order_audit_log(order_id, event_time DESC);

CREATE INDEX IF NOT EXISTS idx_order_audit_log_event_time
    ON order_audit_log(event_time DESC);

CREATE INDEX IF NOT EXISTS idx_order_audit_log_symbol
    ON order_audit_log(symbol, event_time DESC);

COMMIT;
