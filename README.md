# cryptotrader

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
