# CryptoTrader Architecture Map

Brutally honest map of the trading system. Updated 2026-05-26.
Focus on what matters for large changes.

---

## High-Level Flow

```
[Market Data] -> [Features/Indicators] -> [Scoring/Ranking] -> [AI Consensus] -> [Risk] -> [Execution]
     ^                  |                        |                  |              |           |
     |                  v                        v                  v              v           v
[WebSocket/REST]  [RSI/MACD/BB/Stoch/ATR]  [Weighted Score]  [4-Role Voting]  [Limits]   [Paper/Live]
     |                                                                                     |
     v                                                                                     v
[PostgreSQL]  <--------------------- Audit / Positions / Trades -------------------------> [Exchange]
```

---

## 1. DATA INGESTION

**Sources:**
- Bitfinex REST API (`cex/bitfinex/api/bitfinex_client_v2.py`) - candles, ticker, order submission
- Bitfinex WebSocket (`cex/bitfinex/api/websocket_client.py`, `api/websocket/bitfinex.py`) - real-time candles
- Binance WebSocket (`api/websocket/binance.py`) - real-time prices
- CoinGecko REST (`core/market_cap/coingecko.py`) - market cap data

**Backfill:**
- `core/market_data/bitfinex_backfill.py` - historical candle backfill
- `core/market_data/binance_backfill.py` - Binance historical data
- `core/market_data/seed_backfill.py` - initial seed data
- `core/market_data/bitfinex_gap_repair.py` - gap detection and repair

**Failure surfaces:**
- WebSocket disconnects silently - no automatic reconnect in all clients
- REST rate limits (unbounded retry exists but no burst control)
- Backfill can stall on network hiccups

---

## 2. FEATURE GENERATION

**Indicators (`core/indicators/`):**
- RSI (`rsi.py`) - overbought/oversold
- MACD (`macd.py`) - momentum crossover
- Bollinger Bands (`bollinger.py`) - volatility breakout
- Stochastic (`stochastic.py`) - momentum oscillator
- ATR (`atr.py`) - volatility measure
- High/Low channel (`high_low.py`) - breakout detection
- Volume spike (in detector)
- MA golden/death cross (in detector)

**Signal Detection (`core/signals/detector.py`):**
- `detect_signals()` runs all indicators on latest candles
- Produces `Opportunity` objects with weighted score (0-100)
- AlertManager sends desktop/webhook/file alerts
- Minimum edge filter: FeeModel gates trades (see Section 8)

**Scoring (`core/signals/scoring.py`):**
- Weighted sum of indicator contributions
- Normalized weights, explainable output
- Edge case: zero weights raise ValueError

**Failure surfaces:**
- Indicators silently return HOLD (no signal) - no alert
- Minimum edge filter now implemented (FeeModel) - weak signals filtered
- Indicator correlation not accounted for (RSI/MACD/Stoch highly correlated)

---

## 3. RANKING

**Opportunity Evaluator (`core/opportunities/evaluator.py`):**
- Ranks signals by score and freshness
- Filters by symbol/timeframe/exchange
- Produces ranked list for AI processing

**Correlation (`core/analysis/correlation.py`):**
- Cross-symbol correlation for portfolio-level decisions
- Cached with TTL (300s)
- Cache key: "symbols:exchange:timeframe:lookback"

**Failure surfaces:**
- Correlation cache can stale during regime changes
- No eviction policy beyond TTL - max 100 entries

---

## 4. SIGNAL GENERATION (Multi-Brain AI)

**Roles (`core/ai/roles/`):**
1. **Screener** (`screener.py`) - macro trend, momentum, market health
2. **Tactical** (`tactical.py`) - entry/exit timing, technical precision
3. **Fundamental** (`fundamental.py`) - value, market cap, fundamentals
4. **Strategist** (`strategist.py`) - portfolio allocation, risk assessment

**Providers (`core/ai/providers/`):**
- OpenAI (`openai.py`)
- OpenRouter (`openrouter.py`)
- DeepSeek (`deepseek.py`)
- xAI (`xai.py`)
- Ollama (`ollama.py`)
- Guardian (local LLM, `guardian.py`) — requires `GUARDIAN_API_KEY` env var.
  Absent key causes short-circuit (no unauthenticated /v1/models polling).

**Consensus (`core/ai/consensus.py`):**
- Weighted voting across roles
- Hard VETO (any role blocks) or Soft VETO (reduces confidence)
- Confidence threshold: 0.6 (configurable, not hardcoded anymore)
- Min agreement: 2 roles
- Agreement multiplier: 1.15x for unanimous
- Historical accuracy calibration (in-memory, not persisted)
- Tie detection between BUY/SELL (returns NEUTRAL on ties below threshold)
- Soft VETO penalty configurable
- Calibration uses exponential moving average (alpha=0.1)

**Failure surfaces:**
- LLM provider failures handled with retry + fallback chain
- Circuit breaker state is instance-level (ephemeral, resets on restart)
- Role accuracy in-memory only - lost on restart
- Kelly default is full (1.0) in sizing.py, but base.py has quarter-Kelly (max 0.25)
- Multi-brain is expensive: 4 LLMs per evaluation in parallel

---

## 5. EXECUTION PATH

**Orchestrator (`core/automation/orchestrator.py`):**
- Main trading loop daemon
- Polls at configurable interval (default 60s)
- For each symbol: fetch candles -> calculate indicators -> get signal -> check safety -> execute
- Human approval gate for large trades (approval_threshold)
- Supports both paper and live (Bitfinex) execution

**Execution flow:**
1. Fetch latest candles (REST or WebSocket)
2. Calculate indicators
3. Generate signal
4. Get current price
5. Build OrderIntent (amount = position_size / price)
6. Run safety checks (7 checks)
7. Human approval gate (if threshold set)
8. Execute (paper or live)
9. Update position state

**Executors:**
- Paper (`core/execution/paper.py`) - in-memory with optional DB persistence
- Bitfinex Live (`core/execution/bitfinex_live.py`) - real orders with dry-run support
- Legacy dry-run (`core/execution/paper.py` LegacyPaperExecutor)

**Failure surfaces:**
- Paper executor: in-memory by default, DB persistence optional
- Live execution requires valid API credentials
- No automatic retry on execution failures
- Only Bitfinex supported for live trading

---

## 6. EXCHANGE INTEGRATION

**Bitfinex (`cex/bitfinex/`):**
- V2 API client with auth, candles, ticker, order submission
- WebSocket client for real-time data
- Support for market and limit orders
- EXCHANGE MARKET / EXCHANGE LIMIT order types

**Binance (`api/websocket/binance.py`):**
- Price streaming via WebSocket
- Used for multi-exchange price comparison

**Failure surfaces:**
- Bitfinex auth tokens expire - no automatic refresh
- WebSocket reconnection not universal across all clients
- Margin trading out of scope (spot only)
- Single exchange dependency (Bitfinex primary)

---

## 7. WALLET AND PORTFOLIO FLOW

**Portfolio Manager (`core/portfolio/manager.py`):**
- Central coordinator for balances, positions, equity
- Long/short position tracking
- Realized/unrealized P&L
- Equity curve snapshots

**Balance Manager (`core/portfolio/balances.py`):**
- Available/reserved balance tracking
- Deposit/withdraw operations

**Position Manager (`core/portfolio/positions.py`):**
- Open/close positions with P&L calculation
- Partial closes supported

**Wallet Snapshots (`core/portfolio/snapshots.py`):**
- Periodic snapshots (default 1h, on-trade too)
- Equity curve tracking with drawdown

**Paper Position Tracking (`core/execution/paper.py`):**
- PaperPosition: symbol, qty, avg_entry, realized_pnl
- PaperOrder: order_id, symbol, side, type, qty, limit_price, status, fill_price, slippage
- Supports long/short, position flipping, partial closes
- P&L = (current_price - avg_entry) * qty

**Failure surfaces:**
- Minimum edge filter now implemented (FeeModel)
- Balance check is simplified (assumes quote currency)
- No live drawdown monitoring as a trading signal (tracked but not used in execution)

---

## 8. RISK CONTROLS

**Safety Checks (`core/automation/safety.py`):**
1. Kill Switch - global enable/disable, per-symbol
2. Position Size - max position value per symbol (FIXED: now uses notional = amount * price)
3. Cooldown - min seconds between trades
4. Daily Trade Count - per-symbol and global limits
5. Balance - minimum balance required (notional-aware)
6. Daily Loss - max loss per day
7. Slippage - max slippage in basis points

**Risk Limits (`core/risk/limits.py`):**
- ExposureChecker validates position size, total exposure, position count
- Pure data model, no side effects

**Position Sizing (`core/risk/sizing.py`):**
- Fixed fractional - risk X% of portfolio
- Kelly criterion - optimal sizing based on win rate (default full 1.0)
- ATR-based - volatility-adjusted sizing

**Drawdown (`core/risk/drawdown.py`):**
- DrawdownMonitor class with daily and total drawdown
- Trading pause and kill switch activation
- In-memory only (not persisted)
- Trailing stop support

**Fee Model (`core/fees/model.py`):**
- Maker/taker fee rates
- Spread and slippage costs
- Minimum edge calculation: total_cost / gross_notional
- minimum_edge_threshold_bps() helper
- Fee model gates trades: trade only fires if expected edge > costs

**FIXED since last map:**
- PositionSizeCheck: now uses `intent.amount * current_price` (notional), not just `intent.amount`
- TradeHistory: bounded at 10,000 entries, 30-day age limit, auto-prune
- FeeModel: full implementation (not scaffolding)

**Still broken:**
- Kelly default is full (1.0) - aggressive sizing
- No minimum edge filter integration in the main signal path (FeeModel exists but not wired to all signal paths)
- No live drawdown monitoring as a trading signal (tracked but not used)

---

## 9. DATABASE AND STORAGE

**PostgreSQL (`core/storage/postgres/`):**
- Single PostgresStores entrypoint (multiple protocol mixins)
- SQLAlchemy engine with pre-ping, SSL support
- Connection timeout: 3s

**Tables:**
- candles - OHLCV data (upsert by exchange+symbol+timeframe+open_time)
- opportunities - detected trading opportunities
- market_data_jobs - ingestion job tracking
- candle_gaps - gap detection/repair records
- paper_orders - paper trading orders (with DB persistence)
- paper_positions - paper trading positions (with DB persistence)
- orders, positions, trades, audit_events, fee_schedules (skeleton implementations)

**Key methods:**
- upsert_candles() - bulk upsert with ON CONFLICT
- get_candles() - range query by time
- log_opportunity() / get_opportunities() - opportunity persistence
- create_job() / update_job_status() - job tracking

**Failure surfaces:**
- Many methods are skeleton/placeholder (log_intent, log_result, log_event, etc.)
- No connection pool monitoring - stale connections possible
- SSL config from env vars (PGSSLMODE, etc.)

---

## 10. OBSERVABILITY

**Health Checks (`core/health/checker.py`, `api/routes/health.py`):**
- /health - database connectivity + schema check
- /healthz - alias for /health
- /system/status - comprehensive backend + DB health
- /ingestion/status - candle freshness per symbol/timeframe
- /gaps/summary - candle gap stats

**Audit Logging (`core/automation/audit.py`):**
- AuditEvent model with severity levels
- AuditLogger records trade decisions, rejections, errors
- Structured logging with context

**Signal Alerts (`core/signals/detector.py`):**
- Desktop notifications (plyer or notify-send)
- File logging (logs/signals.log)
- Webhook notifications (Discord/Slack)
- Configurable via env vars

**Notifications (`core/notifications/`):**
- Telegram (`telegram.py`)
- Discord (`discord.py`)
- Dispatcher (`dispatcher.py`) - unified notification routing

**Failure surfaces:**
- AlertManager can fail silently (try/except around each notification)
- Webhook notifications depend on requests library availability
- No metrics collection (Prometheus, Datadog, etc.)

---

## 11. DEPLOYMENT

**Services:**
- FastAPI main app (`api/main.py`) - HTTP API + WebSocket
- Strategy Orchestrator (`core/automation/orchestrator.py`) - trading loop daemon
- WebSocket Manager (`api/websocket/manager.py`) - multi-exchange price streaming

**Entry Points:**
- `scripts/run_api.py` - start the API server
- `scripts/run_backtest.py` - run backtests
- `scripts/healthcheck.py` - health check script
- `scripts/install_services.py` - systemd service installation

**Configuration:**
- Environment variables (DATABASE_URL, BITFINEX_API_KEY, etc.)
- SSL/TLS via libpq env vars
- Rate limiting via middleware

**Failure surfaces:**
- No orchestrator auto-restart configured
- No graceful shutdown (lifespan exists but minimal)
- Market cap cache TTL is 10 minutes (stale during market events)

---

## 12. FAILURE SURFACES (Ranked by Impact)

### Critical
1. ~~**PositionSizeCheck bug** - FIXED: now uses notional (amount * price)~~
2. ~~**TradeHistory memory leak** - FIXED: bounded at 10K entries, 30 days~~
3. **No minimum edge filter in signal path** - FeeModel exists but not wired to all signal paths
4. **Kelly full (1.0)** - aggressive sizing, no fractional Kelly default
5. **No live drawdown monitoring** - tracked but not used as trading signal

### High
6. **LLM provider cascading failures** - no circuit breaker (state is ephemeral)
7. **Role accuracy in-memory** - lost on restart
8. **Paper executor in-memory** - optional DB persistence
9. **WebSocket reconnection gaps** - not all clients reconnect
10. **Single exchange dependency** - Bitfinex only for live trading

### Medium
11. **Correlation cache staleness** - no eviction policy
12. **Many Postgres methods skeleton** - placeholder implementations
13. **Fee model minimal** - works but not comprehensive (no dynamic fee tiers)
14. **Balance check simplified** - assumes quote currency
15. **Indicator correlation ignored** - RSI/MACD/Stoch are correlated but count as separate votes
16. **No walk-forward analysis** - backtest results may be overfitted

---

## 13. HIGHEST-LEVERAGE REVIEW TARGETS

Before making large changes, review these files first:

| Priority | File | Why |
|----------|------|-----|
| 1 | `core/automation/safety.py` | All safety checks converge here. PositionSizeCheck fixed. |
| 2 | `core/automation/rules.py` | TradeHistory bounded, config model. |
| 3 | `core/ai/consensus.py` | Thresholds, calibration logic, tie handling. |
| 4 | `core/ai/roles/base.py` | Kelly sizing, role registry, calibration. |
| 5 | `core/risk/sizing.py` | Kelly fraction, ATR sizing. |
| 6 | `core/signals/detector.py` | Signal detection, alerting, minimum edge. |
| 7 | `core/fees/model.py` | Fee/cost model - minimum edge calculation. |
| 8 | `core/execution/paper.py` | Paper executor - position tracking, P&L. |
| 9 | `core/storage/postgres/stores.py` | Database persistence layer. |
| 10 | `core/automation/orchestrator.py` | Main trading loop, integration point. |

---

## 14. DEPENDENCY MAP

```
api/
  main.py -> routes/* -> websocket/*
  candle_stream.py
  routes/
    ai.py -> core/ai/*
    alerts.py -> core/alerts/*
    arbitrage.py -> core/arbitrage/*
    backtest.py -> core/backtest/*
    portfolio.py -> core/portfolio/*
    trade_history.py -> db/crud/*
    ws.py -> api/websocket/*
    health.py -> core/health/*
    export.py -> core/export/*
    notifications.py -> core/notifications/*
    ratelimit.py -> core/ratelimit/*
    fees.py -> core/fees/*

cex/
  bitfinex/
    api/
      bitfinex_client_v2.py -> execution
      websocket_client.py -> streaming
      auth.py -> credentials

core/
  ai/
    consensus.py -> scoring
    roles/* -> multi-brain
    providers/* -> LLM backends
    router.py -> routing
  automation/
    orchestrator.py -> main loop
    safety.py -> risk checks
    rules.py -> config
    audit.py -> logging
  signals/
    detector.py -> detection
    scoring.py -> weighted score
    weights.py -> indicator weights
  execution/
    interfaces.py -> protocols
    paper.py -> paper trading
    bitfinex_live.py -> live trading
    order_book.py -> order management
  portfolio/
    manager.py -> central
    balances.py -> cash
    positions.py -> open positions
    pnl.py -> P&L
    snapshots.py -> equity curve
  risk/
    sizing.py -> Kelly/fixed/ATR
    limits.py -> exposure
    drawdown.py -> drawdown tracking
  fees/
    model.py -> fee/cost calculation
  market_data/
    websocket_provider.py -> real-time
    bitfinex_backfill.py -> historical
    bitfinex_gap_repair.py -> gap repair
  storage/postgres/
    stores.py -> persistence
    config.py -> connection
  indicators/
    rsi.py, macd.py, bollinger.py, stochastic.py, atr.py, high_low.py
  backtest/
    engine.py -> backtest engine
    strategy.py -> strategy definitions
    metrics.py -> performance metrics
    report.py -> backtest reports
  notifications/
    telegram.py, discord.py, dispatcher.py

db/
  crud/* -> data access
  models/* -> ORM models
  init_db.py -> initialization

strategies/
  rsi_mean_reversion.py
  sma_crossover.py

shared/
  technical_indicators.py -> shared indicator functions
  indicator_config.py -> indicator configuration
```

---

## 15. WHAT'S CHANGED (vs previous map)

**FIXED:**
- PositionSizeCheck: uses notional (amount * price), not raw amount
- TradeHistory: bounded list with auto-prune (max 10K entries, 30 days)
- FeeModel: full implementation (maker/taker, spread, slippage, min edge)

**STILL BROKEN:**
- Kelly default is full (1.0) - aggressive
- No minimum edge filter in main signal path
- No live drawdown monitoring as trading signal
- Role accuracy in-memory only
- Circuit breaker state ephemeral
- Many Postgres methods are skeleton/placeholder

**NEW:**
- DrawdownMonitor class (daily + total drawdown with pause)
- Paper executor optional DB persistence
- Human approval gate for large trades
- Consensus tie detection
- Soft VETO penalty configurable
- MA golden/death cross and volume spike indicators
