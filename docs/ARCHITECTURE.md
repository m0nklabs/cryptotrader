# Architecture

## Scope (v2)

This repository is a v2 trading system focused on:

- Market data ingestion (OHLCV candles)
- Technical analysis (indicator computation)
- Opportunity scoring (signal generation)
- API-based execution with **paper-trading / dry-run by default**

Out of scope for v2:

- DEX / swaps / bridges / tokenomics

Notes:

- Some historical material mentions arbitrage. In v2 we treat this as optional CEX-only strategy work. Anything DEX/bridge/swap-related remains out of scope.

## High-level flow

1. **Market data** (CEX public endpoints)
   - Fetch OHLCV candles per symbol + timeframe
   - Normalize to a canonical candle DataFrame

2. **Indicators / TA**
   - Compute indicator values from candles (RSI, MACD, Stochastic, MA, Bollinger, ATR, volume signals, etc.)

3. **Signals & opportunity scoring**
   - Produce human-readable reasons ("why")
   - Aggregate into a confidence score (0-100)

4. **Execution (paper by default)**
   - Convert signals into orders
   - Apply safety checks
   - Log intent + outcome

5. **Fees & costs (always-on)**
   - Model maker/taker fees, funding, withdrawal/deposit fees (where applicable)
   - Include spread + slippage assumptions
   - Compute net edge thresholds before executing

## Data model

### Candles (OHLCV)

Industry-standard indicators need OHLCV (not only last price).

Recommended candle schema (logical):

- `symbol` (e.g., `BTCUSD`)
- `exchange` (e.g., `bitfinex`, `binance`, or `aggregate`)
- `timeframe` (e.g., `1m`, `5m`, `15m`, `1h`, `4h`, `1d`)
- `open_time`, `close_time`
- `open`, `high`, `low`, `close`, `volume`

Optional indexes (if stored in a DB):

- `(symbol, timeframe, open_time DESC)`
- `(symbol, exchange, timeframe, open_time)`

Concrete table example (PostgreSQL-style, optional):

```sql
CREATE TABLE candles (
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
   UNIQUE(exchange, symbol, timeframe, open_time)
);

CREATE INDEX idx_candles_symbol_tf_time
   ON candles(symbol, timeframe, open_time DESC);
CREATE INDEX idx_candles_lookup
   ON candles(exchange, symbol, timeframe, open_time);
```

### Indicator weights (optional DB)

Indicator weights can be configured dynamically.

- Default: hardcoded weights (works offline)
- Optional: configure via DB when `DATABASE_URL` is set

The design intent is:

- Store registered indicators and metadata
- Store per-user / per-strategy weight overrides
- Log historical signals for backtesting/optimization

Concrete tables expected by `shared/indicator_config.py` (PostgreSQL-style):

```sql
CREATE TABLE indicators (
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

CREATE TABLE indicator_weights (
   id SERIAL PRIMARY KEY,
   indicator_id INTEGER NOT NULL REFERENCES indicators(id) ON DELETE CASCADE,
   user_id INTEGER NOT NULL,
   weight DECIMAL(3,2) NOT NULL,
   strategy VARCHAR(50) DEFAULT 'default',
   notes TEXT,
   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
   UNIQUE(indicator_id, user_id, strategy)
);

-- Note: current v2 code logs by `coin_id` (legacy-style). If you want symbol-based
-- logging, switch the column to `symbol VARCHAR(50)` and update the logger.
CREATE TABLE indicator_signals (
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

CREATE INDEX idx_indicator_signals_lookup
   ON indicator_signals(indicator_id, coin_id, timeframe, timestamp);
```

### Fees and execution costs

Fees are a first-class concern because they determine whether an opportunity is actionable.

Minimum expected components:

- Exchange trading fees (maker/taker)
- Spread assumptions
- Slippage assumptions
- Funding/financing costs (where relevant)
- Transfer/withdrawal fees (when moving between venues)

Minimum deliverables:

- A fee/cost model that outputs an estimated total cost for a proposed trade notional
- A minimum required edge threshold ("don’t trade unless expected edge > costs")

## Signals & scoring

A practical industry pattern is:

- Each indicator produces:
  - `signal` (BUY/SELL/HOLD/CONFIRM)
  - `strength` (0-100)
  - `reason` (human readable)
- Combine using normalized weights:

$\text{score} = \sum_i w_i \cdot s_i$

Where $\sum_i w_i = 1$ and $s_i \in [0,100]$.

## Automation & execution

### Rule / policy model (conceptual)

Even for pure TA execution, having an explicit policy layer helps safety:

- Enable/disable automation globally
- Per-symbol configuration (max size, max daily trades, cooldown)
- Slippage guards and timeouts

See:

- The automation engine must include explicit safety checks, rule toggles, cooldowns, daily limits, slippage guards, and audit logging.

### Safety controls (baseline)

- Kill switch (global disable)
- Position sizing limits
- Cooldowns and daily limits
- Slippage/price deviation checks
- Order status tracking and timeouts

## Current implementation mapping

- TA: `shared/technical_indicators.py`
- Optional weights/config: `shared/indicator_config.py` (uses `DATABASE_URL` when present)
- CEX API client: `cex/bitfinex/api/bitfinex_client_v2.py`

## Frontend dashboard

This repo includes a minimal dashboard UI under `frontend/`:

- Sticky header/footer, MT4/5-inspired dock layout
- Dark mode + collapsible panels
- Minimal settings popup in the header

Operational notes (ports + service wiring) live in `docs/OPERATIONS.md`.

## Core module skeleton (implementation targets)

The v2 core is being built as a set of small, delegatable modules:

- `core/market_data/`: OHLCV ingestion + normalization (provider interfaces)
- `core/fees/`: fee/cost estimation and minimum edge thresholds
- `core/signals/`: signal aggregation and scoring
- `core/execution/`: paper/live execution adapters (paper by default)
- `core/automation/`: policy + safety checks (dry-run by default)
- `core/risk/`: risk limits models
- `core/portfolio/`: positions/balances interfaces
- `core/persistence/`: persistence boundary (interfaces)
- `core/storage/`: reserved for concrete persistence implementations

Each module should be implemented against the requirements described in this document and in `docs/TODO.md`.

## Feature set (complete list)

This is the complete intended feature scope for v2 (DEX/swaps/bridges/tokenomics excluded):

### Market data & storage

- OHLCV candle ingestion (CEX public endpoints)
- Candle backfill (batch download)
- Gap detection and data-quality checks
- Optional persistence (DB) for candles, signals, and audit logs

### Technical indicators & signals

- Indicator computation on OHLCV (RSI, MACD, Stochastic, MAs, Bollinger, ATR, volume signals, etc.)
- Signal generation with:
   - `signal` (BUY/SELL/HOLD/CONFIRM)
   - `strength` (0-100)
   - human-readable `reason`
- Aggregation into an overall opportunity score (0-100)

### Indicator weights (configurable)

- Default weights in code (works offline)
- Optional DB-driven indicator metadata + per-user/per-strategy weights
- Auto-normalization (weights sum to 1)
- Historical signal logging (for backtesting/optimization)

### Fees & edge thresholds

- Trading fees (maker/taker)
- Spread + slippage assumptions
- Optional funding/financing costs
- Optional transfer/withdrawal fees (when moving venues)
- Net edge computation + minimum required edge thresholds

### Automation engine

- Rule/policy configuration (enable/disable, symbol scope, size limits)
- Safety checks (balances, cooldowns, daily trade/loss limits)
- Slippage guards and timeouts
- Execution monitoring (order status tracking)
- Audit logging for every decision step
- Kill switch

### Execution

- Paper-trading/dry-run executor (default)
- Exchange adapters (Bitfinex first)
- Clear separation between signal generation and execution side-effects

### Multi-exchange

- Additional CEX integrations (planned)
- Common interfaces for market data and execution adapters

### Operations

- Operational runbook basics (service wiring later)

For actionable work packages, see `docs/TODO.md`.
