# Development setup

See `docs/ARCHITECTURE.md` for the system overview.

## Python environment

This repo uses a local virtual environment.

- Create venv (if not present):
  - `python -m venv .venv`
- Activate:
  - `source .venv/bin/activate`
- Install dependencies:
  - `pip install -r requirements.txt`

## Quick sanity check

Run an import smoke test:

- `python -c "import shared.technical_indicators, shared.indicator_config; from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient; print('imports-ok')"`

## Quality gate (lint + tests)

- Install dev deps: `pip install -r requirements-dev.txt`
- Lint: `ruff check .`
- Tests: `pytest`
- Run both: `ruff check . && pytest`

### What's validated

The quality gate ensures:
- **Code style**: Ruff checks for PEP 8 compliance and common errors (E, F rules)
- **Correctness**: 495+ unit tests covering:
  - Technical indicators (RSI, MACD, Bollinger, ATR, Stochastic)
  - Signal detection and scoring
  - API endpoints (health, candles, fees)
  - Market data ingestion and backfill
  - PostgresStores timezone normalization (critical for --resume)
  - WebSocket providers
  - Portfolio and risk management
  - Paper trading execution

### CI/CD

GitHub Actions runs the quality gate on every push and PR:
- `.github/workflows/ci.yml` - Ruff + pytest (unit + integration)
- See workflow runs at: https://github.com/m0nk111/cryptotrader/actions

## Bitfinex API credentials

The Bitfinex client supports both public and authenticated (read-only) endpoints.

**Environment variables** (set in `.env` or shell, never commit secrets):

- `BITFINEX_API_KEY` - Your Bitfinex API key
- `BITFINEX_API_SECRET` - Your Bitfinex API secret
- Alternative env var names also supported: `BITFINEX_API_KEY_MAIN`, `BITFINEX_API_KEY_SUB`, `BITFINEX_API_KEY_TEST`, etc.

**Usage example** (authenticated read-only endpoint):

```python
from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient

# Client reads credentials from environment variables
client = BitfinexClient()

# Or pass credentials explicitly (not recommended, prefer env vars)
# client = BitfinexClient(api_key="...", api_secret="...")

# Get wallet balances (read-only, safe)
wallets = client.get_wallets()
for wallet in wallets:
    print(f"{wallet['type']:10} {wallet['currency']:6} {wallet['balance']:>12.8f}")
```

**Security notes**:

- Never log or print API keys/secrets
- Only read-only endpoints are implemented (wallets, account info)
- Trading/execution endpoints are intentionally excluded to prevent accidental live trading
- Use separate API keys with read-only permissions when possible

## Bitfinex candle download smoke test (no DB)

To verify you can download candles from Bitfinex public endpoints without configuring Postgres:

- `python scripts/bitfinex_candles_smoke.py --symbol BTCUSD --timeframe 1m --minutes 10 --limit 10`

## Optional database

The v2 skeleton includes a minimal PostgreSQL-style schema for:

- OHLCV candles (`candles`)
- Reference tables (`exchanges`, `symbols`, `strategies`)
- Market-data job tracking (`market_data_jobs`, `market_data_job_runs`)
- Data-quality gap tracking (`candle_gaps`)
- Indicator config/weights/signals (`indicators`, `indicator_weights`, `indicator_signals`)
- Opportunity snapshots (`opportunities`)
- Execution audit trail (`execution_intents`, `execution_results`)
- Generic audit events (`audit_events`)
- Portfolio snapshots (`wallet_snapshots`, `positions`)
- Orders and fills (`orders`, `trade_fills`)
- Fee schedules (`fee_schedules`)

To apply the schema:

- Set `DATABASE_URL` (see `.env.example`)
- Install optional deps: `pip install SQLAlchemy psycopg2-binary`
- Run: `python -m db.init_db`

### Database healthcheck

To validate DB connectivity and ingestion freshness:

- `python scripts/db_health_check.py --exchange bitfinex --symbol BTCUSD --timeframe 1h`

This script checks:

- DB connectivity (db-ok / db-fail)
- Schema status (candles table exists)
- Total candles count
- Latest candle open_time for a given exchange/symbol/timeframe

Exit codes:

- 0 = success
- 1 = failure (DB connectivity, schema, or other error)

Notes:

- Does not print DATABASE_URL or any secret values
- Works with local docker-compose Postgres setup

### Ingestion report

To print a compact ingestion summary for exchange/symbol/timeframe tuples:

- `python scripts/ingestion_report.py --exchange bitfinex --symbol BTCUSD --timeframe 1h`

This script checks:

- DB connectivity
- Schema status (candles table exists)
- Total candles count
- Latest candle open_time for a given exchange/symbol/timeframe

Exit codes:

- 0 = success
- 1 = failure (DB connectivity, schema, or other error)

Notes:

- Does not print DATABASE_URL or any secret values
- Works with local docker-compose Postgres setup

### Historical candles backfill (Bitfinex → Postgres)

This job fetches historical OHLCV candles from Bitfinex public endpoints and upserts them into the `candles` table.
It also logs `market_data_jobs` and `market_data_job_runs`.

Prereqs:

- `DATABASE_URL` set
- Schema applied (`python -m db.init_db`)

Run:

- `python -m core.market_data.bitfinex_backfill --symbol BTCUSD --timeframe 1h --start 2025-01-01 --end 2025-02-01`

Resume (continue from latest candle in DB):

- `python -m core.market_data.bitfinex_backfill --symbol BTCUSD --timeframe 1h --resume`

### Seed backfill (batched with rate-limit friendly jitter)

For initial DB bootstrapping without manual date management, use the seed backfill helper that splits large lookback periods into small batches with sleep/jitter between requests to respect Bitfinex rate limits.

Prereqs:

- `DATABASE_URL` set
- Schema applied (`python -m db.init_db`)

Run (e.g. seed 7 days of 1h candles in 3-hour chunks with 2s sleep):

- `python -m core.market_data.seed_backfill --symbol BTCUSD --timeframe 1h --days 7 --chunk-minutes 180 --sleep-seconds 2.0`

Run (e.g. seed 30 days of 5m candles in 6-hour chunks with 3s sleep):

- `python -m core.market_data.seed_backfill --symbol ETHUSD --timeframe 5m --days 30 --chunk-minutes 360 --sleep-seconds 3.0`

Resume (backfill only the missing gap to reach target lookback):

- `python -m core.market_data.seed_backfill --symbol BTCUSD --timeframe 1h --days 7 --resume`

Notes:

- Uses existing `run_backfill()` logic; avoids duplicate inserts via upsert.
- Sleep includes ±20% jitter to reduce rate-limit collisions.
- Emits compact progress lines (no secrets).
- Resumable: if you already have 3 days of data and request 7 days, it only backfills the missing 4 days.

### Bootstrap multiple symbols for charts

To populate the DB with a curated list of symbols (so they appear in the dashboard Market Watch), use:

- `python scripts/bootstrap_symbols.py --timeframe 1m --lookback-days 3 --enable-gap-repair`

### Candle gap detect + repair (Postgres + Bitfinex)

This job detects missing `open_time` rows in `candles` for a given range using PostgreSQL `generate_series`, logs them into `candle_gaps`, and optionally repairs them by fetching the missing candles from Bitfinex and upserting.

Detect + repair:

- `python -m core.market_data.bitfinex_gap_repair --symbol BTCUSD --timeframe 1h --start 2025-01-01 --end 2025-02-01`

Resume (scan recent range, default 30 days):

- `python -m core.market_data.bitfinex_gap_repair --symbol BTCUSD --timeframe 1h --resume`

Detect-only:

- `python -m core.market_data.bitfinex_gap_repair --symbol BTCUSD --timeframe 1h --start 2025-01-01 --end 2025-02-01 --detect-only`

## Read-only API (FastAPI)

This repo includes a minimal read-only API for candles, health checks, and ingestion status.

Prereqs:

- `DATABASE_URL` set (see `.env.example`)
- Install dependencies: `pip install -r requirements.txt`

Run the API server:

- `python scripts/run_api.py`
- Default: binds to `127.0.0.1:8000`
- Custom host/port: `python scripts/run_api.py --host 0.0.0.0 --port 8000`
- Dev mode (auto-reload): `python scripts/run_api.py --reload`

Or directly with uvicorn:

- `uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`

### Endpoints

#### GET /health

Database connectivity and schema check.

```bash
curl http://127.0.0.1:8000/health
```

#### GET /candles/latest

Latest candles for a specific exchange/symbol/timeframe.

Parameters:

- `exchange` (optional, default: "bitfinex"): Exchange name
- `symbol` (required): Trading symbol (e.g., BTCUSD)
- `timeframe` (required): Timeframe (e.g., 1m, 5m, 1h)
- `limit` (optional, default: 100, max: 5000): Number of candles

```bash
curl "http://127.0.0.1:8000/candles/latest?symbol=BTCUSD&timeframe=1h&limit=50"
```

#### GET /ingestion/status

Query ingestion freshness for a specific exchange/symbol/timeframe.

Parameters:

- `exchange` (optional, default: "bitfinex"): Exchange name
- `symbol` (required): Trading symbol (e.g., BTCUSD)
- `timeframe` (required): Timeframe (e.g., 1m, 1h)

```bash
curl "http://127.0.0.1:8000/ingestion/status?symbol=BTCUSD&timeframe=1m"
```

Response:

```json
{
  "latest_candle_open_time": 1704110400000,
  "candles_count": 1440,
  "schema_ok": true,
  "db_ok": true
}
```

Fields:

- `latest_candle_open_time`: Unix timestamp in milliseconds of the latest candle (null if no data)
- `candles_count`: Total number of candles for this exchange/symbol/timeframe
- `schema_ok`: Boolean indicating if the candles table exists
- `db_ok`: Boolean indicating if database connection is working

#### POST /fees/estimate

Estimate trading costs for a given gross notional amount.

Example:

```bash
curl -X POST http://127.0.0.1:8000/fees/estimate \
  -H 'Content-Type: application/json' \
  -d '{
    "taker": true,
    "gross_notional": "1000",
    "currency": "USD",
    "maker_fee_rate": "0.001",
    "taker_fee_rate": "0.002",
    "assumed_spread_bps": 5,
    "assumed_slippage_bps": 10
  }'
```

Response:

```json
{
  "fee_total": "2.00000000",
  "spread_cost": "0.50000000",
  "slippage_cost": "1.00000000",
  "minimum_edge_rate": "0.00350000",
  "minimum_edge_bps": "35.00"
}
```

### API docs (interactive)

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### Security notes

- Does not expose DATABASE_URL or other secrets
- Read-only endpoints only (no trading/execution)
- Intended for local network use (no authentication)
