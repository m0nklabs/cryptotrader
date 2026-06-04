# TODO (Feature Backlog & Roadmap)

This document tracks the v2 implementation backlog, priorities, and the path toward the **North Star** goal.

> **See also**: [FEATURES.md](FEATURES.md) for detailed feature documentation.
> **See also**: [ROADMAP_V2.md](ROADMAP_V2.md) for the comprehensive roadmap organized by epics.

---

## 🌟 North Star Goal

**Build a semi-autonomous trading machine that generates consistent profit (PnL).**

The primary metric of success is **profitability**, not just features or code quality. Every new feature must contribute to:

1. **Profit Generation**: Signal quality, execution precision, cost minimization.
2. **Risk Control**: Position sizing, exposure limits, drawdown protection.
3. **Observability**: Real-time transparency into decisions and performance.

### Key Principles

- **Profit > Features**: Prioritize features that directly impact PnL.
- **Paper trading by default**: All execution code defaults to `dry_run=True`.
- **Transparency**: Every decision must be explainable and auditable.
- **Safety first**: Human supervision for large trades or strategy changes.

---

## Constraints

- Default to paper-trading / dry-run.
- Keep secrets out of git.
- DEX/swaps/bridges/tokenomics are out of scope.

---

## 🎯 Strategic Priorities (Ordered by Impact)

This list reflects the May 2026 code audit. It deliberately does not call implemented systems "planned" just because old issues still say so.

### Priority 0: Security and Trustworthiness

- 🔴 Fix #284: `.github/workflows/custom-agent.yml` still interpolates issue comment text inside shell.
- 🔴 Keep all live-money paths dry-run/paper by default until strategy validation is proven.

### Priority 1: Prove Profitability (Backtesting Validation)

The backtest engine and metrics exist. The missing piece is robust validation:

- ✅ Walk-forward and out-of-sample validation (`core/strategy_eval/walk_forward.py`, 33 walk-forward tests).
- ✅ Lookahead-bias tests for indicators, signals, and candle loading.
- ✅ Cost-aware replay using fees, spread, slippage, and realistic fills.
- ✅ Persisted backtest run metadata for comparison over time.

### Priority 2: AI to Paper Execution

Multi-Brain AI is no longer just a skeleton; providers, roles, router, consensus, API, budget checks, and frontend panels exist. The next useful step is controlled integration:

- ⏳ Convert AI consensus into paper-order intents only.
- ⏳ Apply risk gates, VETO state, budget state, and audit logging before any paper order.
- ⏳ Keep live exchange execution explicitly opt-in and operator-approved.

### Priority 3: Database and Runtime Reliability

- ⏳ Disposable PostgreSQL migration/integration tests.
- ⏳ Better coverage for portfolio, trades, AI usage, alert persistence, and candle upserts.
- ⏳ Document the current live stack clearly: Docker PostgreSQL plus native systemd API/frontend.

### Priority 4: Frontend Observability Hardening

The frontend is a broad local dashboard, not a skeleton. The gaps are trust and resilience:

- ⏳ Error boundaries and explicit backend-unavailable states.
- ⏳ Empty/filter states for data-heavy views.
- ⏳ Clear labeling/removal of sample performance data.
- ⏳ Wallet/balance UI stays disabled or explicit until `wallets-data` is deployed.

---

## Feature List (Status Tracking)

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

11. **Risk Management**
    - ✅ Position sizing (Fixed, Kelly, ATR) (`core/risk/sizing.py`)
    - ✅ Exposure limits (`core/risk/limits.py`)
    - ✅ Drawdown controls (`core/risk/drawdown.py`)
    - Documented in `docs/RISK_MANAGEMENT.md`

12. **Market Cap Rankings**
    - ✅ CoinGecko live integration (`core/market_cap/coingecko.py`)
    - ✅ Symbol sorting by market cap
    - Documented in `docs/MARKET_CAP_RANKINGS.md`

### 🚧 In Progress

| Work Item | Issue | Status |
|-----------|-------|--------|
| Multi-exchange support | #131 | Binance/KuCoin adapters in progress |

### 📋 Planned (By Priority)

See [ROADMAP_V2.md](ROADMAP_V2.md) for the audited roadmap and the corrected issue mapping.

The old issue numbers for AI, backtesting, portfolio, and several frontend features are mostly closed. Do not recreate work from old closed issue lists; open small issues for the remaining concrete gaps instead.

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

- **Roadmap**: `docs/ROADMAP_V2.md` (Epic-based roadmap toward North Star)
- **Architecture**: `docs/ARCHITECTURE.md`
- **Development setup**: `docs/DEVELOPMENT.md`
- **Feature status**: `docs/FEATURES.md`
- **Risk management**: `docs/RISK_MANAGEMENT.md`
- **GitHub Issues**: https://github.com/m0nklabs/cryptotrader/issues
