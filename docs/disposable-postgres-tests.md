# Disposable PostgreSQL Integration Tests

## Overview

This document describes the disposable PostgreSQL test path for cryptotrader. It provides a self-contained test environment that:

- Starts a fresh PostgreSQL container on a dedicated port (default: 5433)
- Applies `db/schema.sql` and all migration files from `db/migrations/`
- Runs integration tests that verify both write and read paths
- Cleans up automatically (or can be kept for debugging)

## Key: Disposable vs. Live DB

| Aspect | Disposable Test DB | Live Local DB |
|--------|-------------------|---------------|
| Port | 5433 (configurable) | 5432 |
| Database name | `cryptotrader_test` | `cryptotrader` |
| Data persistence | Ephemeral (tied to container lifecycle) | Persistent |
| Use case | CI, pre-commit, local validation | Production, development |
| Isolation | Full (new container per run) | Shared |
| Schema migrations | Applied fresh each run | Incremental |

## Running Tests

### Single Command

```bash
# All integration tests (auto-starts/stops container)
./scripts/run-integration-tests.sh

# Keep container for debugging
./scripts/run-integration-tests.sh --keep

# Force clean restart (stop existing container first)
./scripts/run-integration-tests.sh --clean

# With custom port
INTEGRATION_PORT=5434 ./scripts/run-integration-tests.sh
```

### Via pytest directly

```bash
# Must have disposable DB running (see conftest.py)
python -m pytest tests/integration/ -v

# With coverage
python -m pytest tests/integration/ --cov=core.storage.postgres --cov-report=term-missing

# Specific test classes
python -m pytest tests/integration/test_postgres_stores.py::TestCandleUpserts -v
python -m pytest tests/integration/test_postgres_stores.py::TestGapDetection -v
python -m pytest tests/integration/test_postgres_stores.py::TestMarketDataJobs -v
python -m pytest tests/integration/test_postgres_stores.py::TestOrdersAndFills -v
python -m pytest tests/integration/test_postgres_stores.py::TestPortfolioSnapshots -v
python -m pytest tests/integration/test_postgres_stores.py::TestAIDecisions -v
python -m pytest tests/integration/test_postgres_stores.py::TestAlerts -v
python -m pytest tests/integration/test_postgres_stores.py::TestTradeHistory -v
python -m pytest tests/integration/test_postgres_stores.py::TestPaperTrading -v
python -m pytest tests/integration/test_postgres_stores.py::TestSchemaVerification -v
python -m pytest tests/integration/test_postgres_stores.py::TestRoundtrip -v
```

### Via Makefile

```bash
# Add to Makefile if desired:
# integration:
#     ./scripts/run-integration-tests.sh
```

## Test Coverage

| Table | Tests | Verify |
|-------|-------|--------|
| `candles` | upsert, query, multi-symbol | Write + read paths, ON CONFLICT |
| `candle_gaps` | log, repair, query, conflict | ON CONFLICT DO UPDATE |
| `market_data_jobs` | create, update, query | Status transitions, filtering |
| `market_data_job_runs` | start, finish, query | Stats tracking |
| `orders` | upsert, query | INSERT/UPDATE, filtering |
| `trade_fills` | upsert, query, order filter | Multi-fill support |
| `portfolio_snapshots` | insert, latest, count | Time-series data |
| `system_prompts` | existence, seeding | AI tables from migration |
| `ai_budget_config` | existence, seeding | Budget configs |
| `pair_predictions` | insert, unique | Prediction timeline |
| `alerts` | existence, insert | Alert conditions |
| `trades` | insert, unique constraint | Trade history |
| `paper_orders` | existence | Paper trading simulation |
| `paper_positions` | existence | Paper positions |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    cryptotrader project                      │
│                                                             │
│  tests/integration/                                         │
│  ├── conftest.py        # Fixtures: container, schema,      │
│  │                       migrations, env override           │
│  ├── test_postgres_stores.py  # Store-level integration     │
│  │                       tests (write + read roundtrip)     │
│  └── test_bitfinex_api.py  # Exchange integration smoke     │
│                          tests (API-key gated)              │
│                                                             │
│  scripts/                                                   │
│  └── run-integration-tests.sh  # Single-command runner      │
│                                                             │
│  db/                                                        │
│  ├── schema.sql           # Core schema (idempotent)        │
│  └── migrations/                                          │
│      ├── 001_ai_tables.sql                                │
│      ├── 002_coin_dossier.sql                               │
│      ├── 003_*.sql          # Multiple migration files      │
│      ├── 005_portfolio.sql                                  │
│      ├── 006_watchlists.sql                                 │
│      └── 007_trade_history.sql                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              Disposable PostgreSQL Container                  │
│              postgres:16-alpine on port 5433                 │
│                                                             │
│  Database: cryptotrader_test                                │
│  User:      cryptotrader                                    │
│  Password:  testpassword123                                 │
│                                                             │
│  Tables: 30+ (core + migration tables)                      │
└─────────────────────────────────────────────────────────────┘
```

## CI Integration

The disposable test path is designed for CI environments:

1. **No shared state** — each run starts fresh
2. **Fast startup** — PostgreSQL container ready in ~5 seconds
3. **Self-contained** — only requires Docker and psql
4. **Deterministic** — schema + migrations applied in order
5. **Clean teardown** — container removed after tests

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `INTEGRATION_PORT` | `5433` | Port for disposable DB |
| `INTEGRATION_DB` | `cryptotrader_test` | Database name |
| `INTEGRATION_USER` | `cryptotrader` | Database user |
| `INTEGRATION_PASS` | `testpassword123` | Database password |
| `PG_VERSION` | `16-alpine` | PostgreSQL image tag |

## Debugging

### Keep container for inspection

```bash
./scripts/run-integration-tests.sh --keep
docker exec -it cryptotrader-integration-db psql -U cryptotrader -d cryptotrader_test
```

### View container logs

```bash
docker logs cryptotrader-integration-db
```

### Connect to running container

```bash
docker exec -it cryptotrader-integration-db psql -U cryptotrader -d cryptotrader_test
```

### Check tables

```sql
-- List all tables
\dt

-- Check row counts
SELECT table_name, (xpath('/row/cnt/text()', xml_count))[1]::text AS count
FROM (
    SELECT table_name, query_to_xml(format('SELECT count(*) FROM %I', table_name), false, true, '') AS xml_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
) t
ORDER BY table_name;
```

## Adding New Tests

1. Add test methods to the appropriate class in `tests/integration/test_postgres_stores.py`
2. Use the `stores` fixture for store-level tests
3. Use `subprocess.run` with `psql` for direct SQL verification
4. Mark slow tests with `@pytest.mark.slow`
5. Run with `--keep` to inspect the DB state after tests

## Relationship to Existing Tests

| Test Type | Location | DB | Scope |
|-----------|----------|----|-------|
| Unit tests | `tests/test_*.py` | Mocked | Fast, isolated |
| Integration tests | `tests/integration/test_postgres_stores.py` | Disposable | Write + read paths |
| API tests | `tests/test_api*.py` | Mocked/TestClient | Endpoint level |
| Bitfinex tests | `tests/integration/test_bitfinex_api.py` | Real API | End-to-end |

The integration tests sit between unit tests (mocked) and end-to-end tests (real API):
- They use a real PostgreSQL database (not mocked)
- They test the actual SQL queries and data flow
- They don't require API keys or network access
- They verify the persistence layer independently of the API layer
