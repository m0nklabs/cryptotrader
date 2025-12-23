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

## Bitfinex candle download smoke test (no DB)

To verify you can download candles from Bitfinex public endpoints without configuring Postgres:

- `python scripts/bitfinex_candles_smoke.py --symbol BTCUSD --timeframe 1m --minutes 10 --limit 10`

## Optional database

### Quick start with docker-compose

For local development, you can spin up a Postgres instance using docker-compose:

**Start Postgres:**

```bash
docker compose up -d postgres
```

**Check status:**

```bash
docker compose ps
```

**Stop Postgres:**

```bash
docker compose down
```

**Connectivity check:**

```bash
docker compose exec postgres psql -U cryptotrader -d cryptotrader -c "SELECT version();"
```

**Configure your environment:**

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Uncomment and use the local docker-compose DATABASE_URL in your `.env`:
   ```
   DATABASE_URL=postgresql://cryptotrader:dev_password_change_me@localhost:5432/cryptotrader
   ```

3. Apply the schema:
   ```bash
   pip install SQLAlchemy psycopg2-binary
   python -m db.init_db
   ```

**Notes:**

- Default credentials are for **local development only** (no production use).
- The `dev_password_change_me` password is safe to commit in `docker-compose.yml` for local dev.
- Frontend dev server runs on port **5176** (see `docs/FRONTEND.md`).

### Schema details

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

### Candle gap detect + repair (Postgres + Bitfinex)

This job detects missing `open_time` rows in `candles` for a given range using PostgreSQL `generate_series`, logs them into `candle_gaps`, and optionally repairs them by fetching the missing candles from Bitfinex and upserting.

Detect + repair:

- `python -m core.market_data.bitfinex_gap_repair --symbol BTCUSD --timeframe 1h --start 2025-01-01 --end 2025-02-01`

Resume (scan recent range, default 30 days):

- `python -m core.market_data.bitfinex_gap_repair --symbol BTCUSD --timeframe 1h --resume`

Detect-only:

- `python -m core.market_data.bitfinex_gap_repair --symbol BTCUSD --timeframe 1h --start 2025-01-01 --end 2025-02-01 --detect-only`

## VS Code terminal stability

If the integrated terminal is unstable/crashing:

- Workspace setting: `terminal.integrated.gpuAcceleration`: `"off"`
- This repo already includes: `.vscode/settings.json`

## Frontend (dashboard skeleton)

There is a minimal dashboard UI skeleton under `frontend/`.

- See: `docs/FRONTEND.md`
