# TODO (feature list + delegation work packages)

This document tracks the v2 implementation backlog with completion status.

> **See also**: [FEATURES.md](FEATURES.md) for detailed feature documentation.

Constraints:

- Default to paper-trading / dry-run.
- Keep secrets out of git.
- DEX/swaps/bridges/tokenomics are out of scope.

## Feature list (with status)

### 🌟 Strategic Goals (North Star)

- **Profit-First Focus**: Shift from pure signal detection to PnL-based optimization.
- **Observability**:
  - ⏳ Real-time frontend with multi-timeframe visualization.
  - ⏳ Wallet/Portfolio overview.
  - ⏳ Indicator overlays & forecast projections.
- **AI & Forecasting**:
  - ⏳ Ollama (local LLM) integration for market sentiment/analysis.
  - ⏳ AI-based opportunity scoring.
  - ⏳ Visual forecasting on charts.

### ✅ Completed

1. **Market data: OHLCV candles**
   - ✅ Fetch candles (public CEX - Bitfinex)
   - ✅ Backfill (`core/market_data/bitfinex_backfill.py`)
   - ✅ Data quality: gap detection (`core/market_data/bitfinex_gap_repair.py`)
   - ✅ Persistence (PostgreSQL via `core/storage/postgres/`)

2. **Technical indicators**
   - ✅ RSI - Relative Strength Index (`core/indicators/rsi.py`)
   - ✅ MACD - Moving Average Convergence Divergence (`core/indicators/macd.py`)
   - ✅ Bollinger Bands (`core/indicators/bollinger.py`)
   - ✅ Stochastic Oscillator (`core/indicators/stochastic.py`)
   - ✅ ATR - Average True Range (`core/indicators/atr.py`)
   - ✅ All produce per-indicator signals (side/strength/reason)

3. **Opportunity scoring**
   - ✅ Weighted aggregation to 0-100 score (`core/signals/scoring.py`)
   - ✅ Output explainability with per-indicator contributions
   - ✅ Signal detection engine (`core/signals/detector.py`)

4. **Indicator weights (configurable)**
   - ✅ Code defaults in `core/signals/weights.py`
   - ✅ Auto-normalize weights
   - ✅ Historical signal logging (`core/signals/history.py`)
   - ⏳ DB-driven weights (schema ready, UI pending)

5. **Fees & cost model**
   - ✅ Maker/taker fees (`core/fees/model.py`)
   - ✅ Spread + slippage assumptions
   - ✅ Net edge threshold calculation
   - ⏳ Funding/financing costs (not yet)
   - ⏳ Transfer/withdrawal fees (not yet)

6. **Automation engine**
   - ✅ Rules/policies (`core/automation/rules.py`)
   - ✅ Safety checks - cooldowns, limits (`core/automation/safety.py`)
   - ✅ Audit logging (`core/automation/audit.py`)
   - ✅ Kill switch (global enabled flag)
   - ⏳ Execution monitoring (partial)

7. **Execution adapters**
   - ✅ Paper executor with order book simulation (`core/execution/paper.py`)
   - ✅ Order book simulation (`core/execution/order_book.py`)
   - ⏳ Bitfinex execution adapter (schema ready)

8. **Multi-exchange** → Issue #131
   - ⏳ Exchange adapter interface (in progress)
   - ⏳ Binance adapter (planned)
   - ⏳ KuCoin adapter (planned)

9. **Operations**
   - ✅ Minimal runbook (`docs/OPERATIONS.md`)
   - ✅ Frontend dashboard on port 5176
   - ✅ Systemd user service templates
   - ⏳ Scheduled jobs for backfill/gap repair

10. **Persistence (DB)**
    - ✅ PostgreSQL schema (`db/schema.sql`)
    - ✅ Candle persistence + gap tracking
    - ✅ Portfolio snapshots
    - ✅ Orders and trade fills
    - ⏳ Full audit logging persistence

### 🚧 In Progress

- Issue #131: Multi-exchange support (Binance adapter)

### 📋 Planned (GitHub Issues)

See [GitHub Issues](https://github.com/m0nklabs/cryptotrader/issues) for full backlog:
- #132: WebSocket real-time prices
- #133: Price and indicator alerts
- #134: Paper trading engine improvements
- #135: Backtesting framework
- #136: Portfolio tracker
- #137: Docker Compose setup
- #138-#148: Additional features

## Work packages (completion status)

| WP | Title | Status | Files |
|----|-------|--------|-------|
| WP1 | Market data (candles) | ✅ Done | `core/market_data/` |
| WP2 | Fees model | ✅ Done | `core/fees/model.py` |
| WP3 | Signal scoring | ✅ Done | `core/signals/scoring.py` |
| WP4 | Paper execution | ✅ Done | `core/execution/paper.py` |
| WP5 | Automation skeleton | ✅ Done | `core/automation/` |
| WP6 | Persistence skeleton | ✅ Done | `db/schema.sql`, `core/storage/` |

---

### WP1 — Market data (candles) ✅

- Targets:
  - `core/market_data/interfaces.py`
  - `core/market_data/bitfinex_backfill.py`
  - `core/market_data/bitfinex_gap_repair.py`
  - `core/market_data/websocket_provider.py`
- Status: **Complete**
- Acceptance:
  - ✅ Fetch OHLCV candles into canonical `core.types.Candle`
  - ✅ Handle timeframe + limit
  - ✅ PostgreSQL persistence via `core/storage/postgres/`

### WP2 — Fees model ✅

- Targets:
  - `core/fees/model.py`
- Status: **Complete**
- Acceptance:
  - ✅ CostEstimate includes trading fees + spread + slippage
  - ✅ Provide min edge threshold helper

### WP3 — Signal scoring ✅

- Targets:
  - `core/signals/scoring.py`
- Status: **Complete**
- Acceptance:
  - ✅ Normalize weights
  - ✅ Score a list of indicator signals to 0-100
  - ✅ Per-indicator contribution breakdown
  - ✅ Human-readable explanation

### WP4 — Paper execution ✅

- Targets:
  - `core/execution/paper.py`
  - `core/execution/order_book.py`
- Status: **Complete**
- Acceptance:
  - ✅ Always dry-run by default
  - ✅ Return structured `ExecutionResult`
  - ✅ Order book simulation with slippage
  - ✅ Position tracking with P&L

### WP5 — Automation skeleton ✅

- Targets:
  - `core/automation/rules.py`
  - `core/automation/safety.py`
  - `core/automation/audit.py`
- Status: **Complete**
- Acceptance:
  - ✅ Rule model with global + per-symbol configs
  - ✅ Safety checks (cooldowns, position limits, daily loss limits)
  - ✅ Audit event structure
  - ✅ Kill switch (global enabled flag)

### WP6 — Persistence skeleton (DB) ✅

- Targets:
  - `db/schema.sql`
  - `db/init_db.py`
  - `core/storage/postgres/`
- Status: **Complete**
- Acceptance:
  - ✅ Schema applies cleanly with `python -m db.init_db`
  - ✅ Protocols cover candles, opportunities, execution, audit, portfolio
  - ✅ No secrets in code

## Tracking

- Canonical architecture: `docs/ARCHITECTURE.md`
- Development setup: `docs/DEVELOPMENT.md`
- Feature status: `docs/FEATURES.md`
- GitHub Issues: https://github.com/m0nklabs/cryptotrader/issues
