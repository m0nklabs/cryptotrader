# cryptotrader

[![CI](https://github.com/m0nk111/cryptotrader/actions/workflows/ci.yml/badge.svg)](https://github.com/m0nk111/cryptotrader/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/m0nk111/cryptotrader/branch/master/graph/badge.svg)](https://codecov.io/gh/m0nk111/cryptotrader)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A v2 trading platform focused on trading opportunities, technical analysis, and API-based execution.

## Scope

- Market data ingestion (OHLCV candles)
  - REST API backfill for historical data
  - WebSocket streaming for real-time updates
- Technical analysis (indicators)
- Opportunity scoring (signals)
- Execution with **paper-trading / dry-run by default**

Out of scope for v2:

- DEX / swaps / bridges / tokenomics
- Arbitrage-specific workflows

## Documentation

- `docs/README.md` (index)
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT.md`

## Quickstart

```bash
# Clone and setup
git clone https://github.com/m0nk111/cryptotrader.git
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

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

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
