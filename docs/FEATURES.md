# Features Status

This document tracks implemented features, their current status, and detailed documentation.

**Last updated**: February 2026

---

## ✅ Implemented & Working

### Market Data Infrastructure

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| Bitfinex OHLCV backfill | ✅ Working | `core/market_data/bitfinex_backfill.py` | REST API with rate limiting |
| Gap detection & repair | ✅ Working | `core/market_data/bitfinex_gap_repair.py` | Detects and fills missing candles |
| WebSocket streaming | ✅ Working | `core/market_data/websocket_provider.py` | Real-time candle updates |
| Multi-timeframe ingestion | ✅ Working | `scripts/ingest_multi_timeframe.py` | 1m, 5m, 15m, 1h, 4h, 1d |
| Bootstrap script | ✅ Working | `scripts/bootstrap_symbols.py` | Initialize symbols + systemd timers |

#### How Market Data Works

```
Bitfinex REST API → bitfinex_backfill.py → PostgreSQL (candles table)
                                              ↓
                  bitfinex_gap_repair.py ← Gap detection query
                                              ↓
Bitfinex WebSocket → websocket_provider.py → Real-time updates
```

**Backfill Usage:**
```bash
# Backfill BTCUSD from January 2024
python -m core.market_data.bitfinex_backfill BTCUSD 1h --start 2024-01-01

# Repair gaps in existing data
python -m core.market_data.bitfinex_gap_repair BTCUSD 1h
```

---

### Technical Indicators

| Indicator | Status | File | Signals |
|-----------|--------|------|---------|
| RSI (14) | ✅ Working | `core/indicators/rsi.py` | Overbought/oversold |
| MACD (12,26,9) | ✅ Working | `core/indicators/macd.py` | Crossover, histogram |
| Stochastic | ✅ Working | `core/indicators/stochastic.py` | %K/%D crossover |
| Bollinger Bands | ✅ Working | `core/indicators/bollinger.py` | Squeeze, breakout |
| ATR | ✅ Working | `core/indicators/atr.py` | Volatility filter |

#### Indicator Details

**RSI (Relative Strength Index)**
- Period: 14 (configurable)
- Signals: `LONG` when RSI < 30 (oversold), `SHORT` when RSI > 70 (overbought)
- Strength: Distance from threshold (0-100)

```python
from core.indicators.rsi import compute_rsi, generate_rsi_signal

rsi_value = compute_rsi(candles, period=14)  # Returns 0-100
signal = generate_rsi_signal(candles, oversold=30, overbought=70)
# Returns: IndicatorSignal(side=LONG, strength=75, reason="RSI oversold at 25.3")
```

**MACD (Moving Average Convergence Divergence)**
- Fast EMA: 12, Slow EMA: 26, Signal: 9
- Signals: `LONG` on bullish crossover, `SHORT` on bearish crossover
- Histogram indicates momentum strength

```python
from core.indicators.macd import compute_macd, generate_macd_signal

macd_line, signal_line, histogram = compute_macd(candles)
signal = generate_macd_signal(candles)
# Returns: IndicatorSignal(side=LONG, strength=60, reason="MACD bullish crossover")
```

**Bollinger Bands**
- Period: 20, Standard Deviations: 2
- Signals: `LONG` when price touches lower band, `SHORT` at upper band
- Squeeze detection for breakout anticipation

```python
from core.indicators.bollinger import compute_bollinger_bands, generate_bollinger_signal

upper, middle, lower = compute_bollinger_bands(candles, period=20, std_dev=2.0)
signal = generate_bollinger_signal(candles)
```

**Stochastic Oscillator**
- %K Period: 14, %D Period: 3
- Signals: `LONG` when %K < 20 and crosses above %D
- Signals: `SHORT` when %K > 80 and crosses below %D

**ATR (Average True Range)**
- Period: 14
- Used as volatility filter, not directional signal
- High ATR = high volatility = wider stops

---

### Signal Detection & Scoring

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| Signal detector | ✅ Working | `core/signals/detector.py` | Multi-indicator signals |
| Opportunity scoring | ✅ Working | `core/signals/scoring.py` | 0-100 confidence score |
| Configurable weights | ✅ Working | `core/signals/weights.py` | Per-indicator weighting |
| Signal history | ✅ Working | `core/signals/history.py` | Historical signal logging |

#### Signal Detection Flow

```
Candles → [RSI, MACD, Stochastic, Bollinger, ATR] → IndicatorSignals[]
                            ↓
                    scoring.py (weighted average)
                            ↓
              Opportunity(score=0-100, explanation="...")
```

**Usage:**
```python
from core.signals.detector import detect_signals
from core.signals.scoring import score_signals
from core.signals.weights import DEFAULT_WEIGHTS

# Detect all indicator signals
signals = detect_signals(candles=candles, symbol="BTCUSD", timeframe="1h")

# Score and aggregate
result = score_signals(signals=signals, weights=DEFAULT_WEIGHTS)
print(f"Score: {result.score}/100")
print(f"Explanation: {result.explanation}")
# Output: "Score: 72/100 - RSI(25): oversold +18, MACD: bullish crossover +22, ..."
```

**Default Weights:**
```python
DEFAULT_WEIGHTS = {
    "RSI": 0.25,
    "MACD": 0.25,
    "STOCHASTIC": 0.20,
    "BOLLINGER": 0.15,
    "ATR": 0.15,
}
```

---

### Execution & Trading

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| Paper trading | ✅ Working | `core/execution/paper.py` | Simulated execution (default) |
| Order book | ✅ Working | `core/execution/order_book.py` | Order tracking |
| Fee model | ✅ Working | `core/fees/model.py` | Maker/taker, slippage |

#### Paper Trading Engine

The `PaperExecutor` simulates order execution without real money:

```python
from core.execution.paper import PaperExecutor
from core.types import OrderIntent
from decimal import Decimal

executor = PaperExecutor(default_slippage_bps=Decimal("5"))

# Place a market order
order = OrderIntent(
    symbol="BTCUSD",
    side="BUY",
    qty=Decimal("0.1"),
    order_type="market",
)
result = executor.execute(order)
# result.dry_run = True, result.accepted = True

# Place a limit order
limit_order = OrderIntent(
    symbol="BTCUSD",
    side="BUY",
    qty=Decimal("0.1"),
    order_type="limit",
    limit_price=Decimal("40000"),
)
order_id = executor.place_limit_order(limit_order)

# Check positions
positions = executor.get_positions()
# Returns: {"BTCUSD": PaperPosition(qty=0.1, avg_entry=42000, realized_pnl=0)}
```

**Features:**
- Market orders: instant fill at current price ± slippage
- Limit orders: fill when price crosses limit level
- Position tracking: long/short with average entry price
- P&L calculation: realized and unrealized

#### Fee Model

```python
from core.fees.model import FeeModel
from decimal import Decimal

fees = FeeModel(
    maker_fee_bps=Decimal("10"),   # 0.10%
    taker_fee_bps=Decimal("20"),   # 0.20%
    spread_bps=Decimal("5"),        # 0.05%
    slippage_bps=Decimal("5"),      # 0.05%
)

# Calculate total cost for a trade
cost = fees.calculate_cost(
    notional=Decimal("10000"),  # $10,000 trade
    is_maker=False,
)
# cost.total_fee = $30 (0.30% of $10,000)
# cost.net_edge_threshold = 0.30% (minimum edge needed to profit)
```

---

### Automation & Safety

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| Rule engine | ✅ Working | `core/automation/rules.py` | Configurable trading rules |
| Safety checks | ✅ Working | `core/automation/safety.py` | Position limits, cooldowns |
| Audit logging | ✅ Working | `core/automation/audit.py` | All actions logged |

#### Safety Configuration

```python
from core.automation.rules import AutomationConfig, SymbolConfig
from decimal import Decimal

config = AutomationConfig(
    enabled=False,  # Kill switch - disabled by default!
    max_position_size_default=Decimal("10000"),  # Max $10k per position
    max_daily_trades_global=10,  # Max 10 trades per day
    cooldown_seconds_default=60,  # 1 minute between trades
    max_daily_loss=Decimal("500"),  # Stop trading after $500 loss
    symbol_configs={
        "BTCUSD": SymbolConfig(
            symbol="BTCUSD",
            enabled=True,
            max_position_size=Decimal("5000"),
            max_daily_trades=5,
        ),
    },
)

# Check if trading is allowed
if config.is_symbol_enabled("BTCUSD"):
    # Execute trade
    pass
```

**Safety Features:**
- **Kill switch**: Global `enabled=False` stops all trading
- **Position limits**: Per-symbol and global max position size
- **Trade limits**: Max trades per day (global and per-symbol)
- **Cooldowns**: Minimum time between trades
- **Loss limits**: Stop trading after max daily loss
- **Balance requirements**: Minimum balance to trade

---

### Database & Persistence

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| PostgreSQL schema | ✅ Working | `db/schema.sql` | Candles, signals, orders |
| DB initialization | ✅ Working | `db/init_db.py` | Schema migration |
| Candle storage | ✅ Working | `core/storage/postgres/` | Async upsert |

#### Database Schema

```sql
-- Main tables
candles (symbol, timeframe, timestamp, open, high, low, close, volume)
signals (id, symbol, timeframe, timestamp, indicator, side, strength, reason)
orders (id, symbol, side, qty, price, status, created_at, filled_at)
positions (id, symbol, qty, avg_entry, realized_pnl)
audit_log (id, event_type, details, timestamp)
```

**Initialize database:**
```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/cryptotrader"
python -m db.init_db
```

---

### API & Backend

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| REST API | ✅ Working | `api/main.py` | FastAPI endpoints |
| SSE streaming | ✅ Working | `api/candle_stream.py` | Server-sent events |
| Health checks | ✅ Working | Built into API | `/health` endpoint |

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Database connectivity check |
| GET | `/candles/latest` | Latest candles (query: symbol, timeframe, limit) |
| GET | `/ingestion/status` | Data freshness status |
| POST | `/orders` | Place paper order |
| GET | `/orders` | List open orders |
| DELETE | `/orders/{id}` | Cancel order |
| GET | `/positions` | List open positions |
| GET | `/market-cap` | CoinGecko market cap rankings |

**Start API server:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

### Frontend Dashboard

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| Candlestick chart | ✅ Working | `frontend/src/components/CandlestickChart.tsx` | lightweight-charts |
| Order form | ✅ Working | `frontend/src/components/OrderForm.tsx` | Paper trading UI |
| Positions table | ✅ Working | `frontend/src/components/PositionsTable.tsx` | Open positions |
| Orders table | ✅ Working | `frontend/src/components/OrdersTable.tsx` | Order history |

**Start frontend:**
```bash
cd frontend
npm install
npm run dev
# Dashboard at http://localhost:5176
```

---

### DevOps & Infrastructure

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| Systemd services | ✅ Working | `systemd/` | User services for ingestion |
| Pre-commit hooks | ✅ Working | `.pre-commit-config.yaml` | ruff, formatting |
| CI workflows | ✅ Working | `.github/workflows/` | Tests, linting |
| DevContainer | ✅ Working | `.devcontainer/` | VS Code dev environment |

---

## 🚧 In Progress

| Feature | Issue | Status |
|---------|-------|--------|
| Multi-exchange (Binance) | #131 | Copilot assigned |

---

## 📋 Planned (Open Issues)

See [GitHub Issues](https://github.com/m0nklabs/cryptotrader/issues) for the full backlog.

### AI & Multi-Brain (#205)
- #205 - Multi-Brain AI Architecture (skeleton committed, 7 phases planned)
  - Provider adapters: DeepSeek, OpenAI, xAI, Ollama (skeleton ✅)
  - Agent roles: Screener, Tactical, Fundamental, Strategist (skeleton ✅)
  - Consensus engine with weighted voting + VETO (skeleton ✅)
  - Versioned prompt registry with DB backend (skeleton ✅)
  - AI API endpoints (planned)
  - AI frontend config panel (skeleton ✅)
  - Signal pipeline integration (planned)
  - Testing + observability (planned)

### High Priority
- #108 - Automated tests + CI pipeline
- #107 - Technical indicators on chart
- #106 - System health panel
- #137 - Docker Compose setup

### Trading Features
- #133 - Price and indicator alerts
- #134 - Paper trading engine improvements
- #135 - Backtesting framework
- #136 - Portfolio tracker
- #141 - Risk calculator

### Market Data
- #132 - WebSocket real-time prices
- #139 - Order book depth chart
- #143 - Cross-exchange arbitrage

### UI/UX
- #138 - Multi-timeframe view
- #140 - Watchlist with favorites
- #142 - Keyboard shortcuts
- #145 - Data export CSV/JSON
- #148 - Drawing tools

### Infrastructure
- #144 - Telegram/Discord notifications
- #146 - Correlation matrix
- #147 - Rate limit monitor

---

## Usage Examples

### Start the backend API
```bash
source .venv/bin/activate
python -m scripts.api_server
# API available at http://localhost:8000
```

### Run signal detection
```bash
python -m scripts.detect_signals --symbol BTCUSD
```

### Backfill historical data
```bash
python -m scripts.ingest_multi_timeframe --symbol BTCUSD --start 2024-01-01
```

### Start frontend
```bash
cd frontend && npm run dev
# Dashboard at http://localhost:5176
```

### Run tests
```bash
pytest tests/ -v
```
