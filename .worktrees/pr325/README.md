# cryptotrader

[![CI](https://github.com/m0nklabs/cryptotrader/actions/workflows/ci.yml/badge.svg)](https://github.com/m0nklabs/cryptotrader/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/m0nklabs/cryptotrader/branch/master/graph/badge.svg)](https://codecov.io/gh/m0nklabs/cryptotrader)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A v2 trading platform focused on **profitability**, technical analysis, and semi-autonomous execution.

## 🌟 North Star Goal

**Build a semi-autonomous trading machine that generates consistent profit (PnL).**

- **Semi-auto**: Human supervision for large trades or strategy changes; automated execution for routine trades.
- **Profit**: Success is measured by PnL, not just features or code quality.
- **Observability**: Full transparency — follow everything in **real-time** on the frontend.
- **AI-Enhanced**: LLM-powered scoring and analysis (Ollama + API providers).

## ✅ Key Achievements

| Component | Status | Description |
|-----------|--------|-------------|
| **Market Data** | ✅ Complete | Multi-timeframe OHLCV ingestion (REST + WebSocket), gap detection/repair |
| **Technical Analysis** | ✅ Complete | RSI, MACD, Bollinger Bands, Stochastic, ATR with standardized signals |
| **Opportunity Scoring** | ✅ Complete | Weighted aggregation (0-100), per-indicator contributions, explainability |
| **Risk Management** | ✅ Complete | Position sizing (Fixed/Kelly/ATR), exposure limits, drawdown controls |
| **Paper Trading** | ✅ Complete | Order book simulation, P&L tracking, safety checks |
| **Market Cap Rankings** | ✅ Complete | Live CoinGecko integration for symbol sorting |
| **Frontend Dashboard** | ✅ Skeleton | Candlestick charts, order form, positions table |

## 🚧 In Progress

- **Multi-Exchange Support** (Issue #131): Binance/KuCoin adapters

## 📋 Roadmap Highlights

See [docs/ROADMAP_V2.md](docs/ROADMAP_V2.md) for the full epic-based roadmap.

### Critical Path
1. **Backtesting Framework** (#135) — Validate profitability before live trading
2. **Live Execution Adapters** — Bitfinex first, then Binance/KuCoin

### AI & LLM Integration
- **Ollama** (local) and **OpenAI/Anthropic** (API) for qualitative analysis
- AI-based opportunity scoring with reasoning

### Frontend Observability
- **Wallet/Portfolio**: Real-time balances, positions, PnL
- **Opportunity Explorer**: Ranked opportunities, click to visualize
- **Indicator Overlays**: RSI, MACD, Bollinger on price charts
- **Visual Projections**: Future price expectations/forecasts
- **Multi-Timeframe**: Context from multiple timeframes on charts

## Scope

- **Market Data & Analysis**
  - Multi-timeframe OHLCV ingestion (REST + WebSocket)
  - Technical analysis (indicators) & Forecasting
  - AI-driven opportunity scoring (LLM integration)

- **Execution & Automation**
  - Semi-autonomous trading engine
  - **Paper-trading / dry-run by default**
  - Profit-first execution logic

- **Observability (Frontend)**
  - Real-time dashboard with multi-timeframe visualization
  - Wallet & Portfolio overview
  - Visual indicator overlays & forecast projections

Out of scope for v2:
- DEX / swaps / bridges / tokenomics
- Arbitrage-specific workflows

## Documentation

- [docs/README.md](docs/README.md) — Documentation index
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System design
- [docs/FEATURES.md](docs/FEATURES.md) — Feature status & details
- [docs/ROADMAP_V2.md](docs/ROADMAP_V2.md) — Epic-based roadmap
- [docs/RISK_MANAGEMENT.md](docs/RISK_MANAGEMENT.md) — Position sizing & limits
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — Development setup

## Quickstart

### Docker (Recommended)

```bash
# Clone and configure
git clone https://github.com/m0nklabs/cryptotrader.git
cd cryptotrader
cp docker-compose.env.example .env
# Edit .env with your settings

# Start all services
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Access services
# - Frontend: http://localhost:5176
# - API (FastAPI, used by the frontend proxy): http://localhost:8000
# - API Docs (FastAPI): http://localhost:8000/docs
# - Legacy dashboard API (optional dev helper): http://localhost:8787

# Seed sample data (optional)
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec api bash -c "export DATABASE_URL=postgresql://cryptotrader:cryptotrader@postgres:5432/cryptotrader && ./scripts/seed-data.sh"
```

See [docs/DOCKER.md](docs/DOCKER.md) for detailed Docker setup and troubleshooting.

### Manual Setup

```bash
# Clone and setup
git clone https://github.com/m0nklabs/cryptotrader.git
cd cryptotrader
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (API keys, database URL, etc.)

# Run tests
pytest

# Start backend
python -m api.main

# (Optional) Start legacy dashboard API (old DB-backed helper)
python scripts/api_server.py --host 127.0.0.1 --port 8787

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

### Running as Services (systemd)

For production, run frontend and backend as systemd user services:

```bash
# Install frontend service (Vite preview on port 5176)
cp systemd/cryptotrader-frontend.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cryptotrader-frontend.service

# Check status
systemctl --user status cryptotrader-frontend.service

# View logs
journalctl --user -u cryptotrader-frontend.service -f
```

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for full operational details.

Or use **DevContainer** in VS Code for a pre-configured environment.

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed setup instructions.

## Market Data Ingestion

cryptotrader supports ingesting candles for multiple timeframes:

**Standard Timeframes**: 1m, 5m, 15m, 1h, 4h, 1d

```bash
# Set up environment
export DATABASE_URL="postgresql://user:pass@localhost:5432/cryptotrader"

# Backfill all timeframes for a symbol
python -m scripts.ingest_multi_timeframe --symbol BTCUSD --start 2024-01-01

# Resume ingestion (fetch from last candle to now)
python -m scripts.ingest_multi_timeframe --symbol BTCUSD --resume

# Multiple symbols
python -m scripts.ingest_multi_timeframe \
  --symbol BTCUSD --symbol ETHUSD --symbol SOLUSD --resume
```

See `scripts/README.md` for detailed ingestion documentation.

## Frontend

A minimal dashboard UI skeleton lives in `frontend/`.
See `docs/FRONTEND.md`.
