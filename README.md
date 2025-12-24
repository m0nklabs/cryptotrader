# cryptotrader

[![CI](https://github.com/m0nk111/cryptotrader/actions/workflows/ci.yml/badge.svg)](https://github.com/m0nk111/cryptotrader/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/m0nk111/cryptotrader/branch/master/graph/badge.svg)](https://codecov.io/gh/m0nk111/cryptotrader)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A v2 trading platform focused on trading opportunities, technical analysis, and API-based execution.

## Scope

- Market data ingestion (OHLCV candles)
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

## Frontend

A minimal dashboard UI skeleton lives in `frontend/`.
See `docs/FRONTEND.md`.
