-- Alerts system tables
-- Supports price and indicator-based alerts with notification history

-- ---------------------------------------------------------------------------
-- Alerts — user-defined alert conditions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL      PRIMARY KEY,
    user_id         TEXT        NULL,                   -- For future multi-user support
    symbol          TEXT        NOT NULL,
    exchange        TEXT        NOT NULL,
    timeframe       TEXT        NOT NULL,               -- e.g., "1m", "5m", "1h"
    
    -- Alert condition
    condition_type  TEXT        NOT NULL,               -- price_above, price_below, rsi_overbought, etc.
    operator        TEXT        NOT NULL,               -- above, below, crosses_above, crosses_below
    threshold_value REAL        NOT NULL,               -- Value to compare against
    indicator_params JSONB      NULL,                   -- Additional params for indicators (e.g., {"period": 14})
    
    -- State
    enabled         BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    triggered_at    TIMESTAMPTZ NULL,                   -- Last time this alert triggered
    trigger_count   INTEGER     NOT NULL DEFAULT 0,
    
    CONSTRAINT valid_condition_type CHECK (
        condition_type IN (
            'price_above', 'price_below',
            'rsi_overbought', 'rsi_oversold',
            'macd_cross_up', 'macd_cross_down'
        )
    ),
    CONSTRAINT valid_operator CHECK (
        operator IN ('above', 'below', 'crosses_above', 'crosses_below')
    )
);

CREATE INDEX IF NOT EXISTS idx_alerts_symbol_exchange ON alerts (symbol, exchange, enabled);
CREATE INDEX IF NOT EXISTS idx_alerts_user_enabled ON alerts (user_id, enabled) WHERE user_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Alert History — record of triggered alerts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alert_history (
    id              SERIAL      PRIMARY KEY,
    alert_id        INTEGER     NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trigger_value   REAL        NOT NULL,               -- Value that triggered the alert
    price           REAL        NOT NULL,               -- Price at trigger time
    message         TEXT        NOT NULL,               -- Human-readable message
    
    CONSTRAINT fk_alert_history_alert
        FOREIGN KEY (alert_id)
        REFERENCES alerts(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alert_history_alert_id ON alert_history (alert_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_history_triggered_at ON alert_history (triggered_at DESC);
