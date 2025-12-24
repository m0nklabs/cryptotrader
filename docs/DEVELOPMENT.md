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

## VS Code terminal stability

If the integrated terminal is unstable/crashing:

- Workspace setting: `terminal.integrated.gpuAcceleration`: "off"
- This repo already includes: `.vscode/settings.json`

## Frontend (dashboard skeleton)

There is a minimal dashboard UI skeleton under `frontend/`.

- See: `docs/FRONTEND.md`
