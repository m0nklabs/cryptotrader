-- Migration 006: Watchlist tables
--
-- Creates tables for:
-- - Watchlists (named lists of symbols)
-- - Watchlist items (symbols within a watchlist)
-- - Column preferences (user-configurable columns)
--
-- Run after: 005_portfolio.sql

BEGIN;

-- Watchlists (e.g., "My Favorites", "Top Gainers")
CREATE TABLE IF NOT EXISTS watchlists (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_watchlists_sort_order
    ON watchlists(sort_order);

-- Watchlist items (symbols in each watchlist)
CREATE TABLE IF NOT EXISTS watchlist_items (
    id BIGSERIAL PRIMARY KEY,
    watchlist_id BIGINT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    sort_order INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_watchlist_items_list_symbol UNIQUE (watchlist_id, exchange, symbol)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id
    ON watchlist_items(watchlist_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol
    ON watchlist_items(symbol);

-- Column preferences (which columns to show in watchlist)
CREATE TABLE IF NOT EXISTS watchlist_column_prefs (
    id BIGSERIAL PRIMARY KEY,
    watchlist_id BIGINT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    column_name VARCHAR(50) NOT NULL,
    is_visible BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    width INTEGER, -- Column width in pixels (optional)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_watchlist_column_prefs_list_column UNIQUE (watchlist_id, column_name)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_column_prefs_watchlist_id
    ON watchlist_column_prefs(watchlist_id, sort_order);

COMMIT;
