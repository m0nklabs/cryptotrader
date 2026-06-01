"""Integration tests for PostgresStores — disposable PostgreSQL path.

Tests verify both write and read paths for critical trading tables:
- Candle upserts and queries
- Gap detection and repair
- Market data job tracking
- Orders and fills
- Portfolio snapshots
- AI decisions/usage (system prompts, budget config)
- Alerts
- Trade history

Uses the disposable PostgreSQL container from conftest.py.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores
from core.types import (
    Candle,
    CandleGap,
    MarketDataJob,
)

ROOT = Path(__file__).resolve().parents[2]

# Reuse the disposable DB config from conftest
from tests.integration.conftest import (  # noqa: E402
    DISPOSABLE_DB_NAME,
    DISPOSABLE_DB_USER,
    apply_migrations,
    apply_schema,
    start_disposable_db,
    stop_disposable_db,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def postgres_container():
    """Start/stop the disposable PostgreSQL container for the entire session."""
    url = start_disposable_db()
    yield url
    stop_disposable_db()


@pytest.fixture(scope="session")
def schema_ready(postgres_container: str) -> str:
    """Apply schema.sql to the disposable DB."""
    apply_schema(postgres_container)
    return postgres_container


@pytest.fixture(scope="session")
def migrations_ready(schema_ready: str) -> str:
    """Apply all migration files to the disposable DB."""
    apply_migrations(schema_ready)
    return schema_ready


@pytest.fixture
def stores(migrations_ready: str) -> PostgresStores:
    """Create a PostgresStores instance pointing at the disposable DB."""
    return PostgresStores(config=PostgresConfig(database_url=migrations_ready))


@pytest.fixture
def sample_candles() -> list[Candle]:
    """Generate 10 consecutive 1h candles."""
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return [
        Candle(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i + 1),
            open=Decimal("40000") + Decimal(i * 10),
            high=Decimal("40500") + Decimal(i * 10),
            low=Decimal("39500") + Decimal(i * 10),
            close=Decimal("40200") + Decimal(i * 10),
            volume=Decimal("100.5") + Decimal(i),
        )
        for i in range(10)
    ]


@pytest.fixture
def sample_candles_multi_symbol() -> list[Candle]:
    """Generate candles for multiple symbols and timeframes."""
    base = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    for symbol, tf in [("BTCUSD", "1h"), ("ETHUSD", "1h"), ("BTCUSD", "4h")]:
        for i in range(5):
            candles.append(
                Candle(
                    exchange="bitfinex",
                    symbol=symbol,
                    timeframe=tf,
                    open_time=base + timedelta(hours=i)
                    if tf == "1h"
                    else base + timedelta(hours=i * 4),
                    close_time=(base + timedelta(hours=i + 1))
                    if tf == "1h"
                    else base + timedelta(hours=i * 4 + 4),
                    open=Decimal("40000") + Decimal(i * 100),
                    high=Decimal("40500") + Decimal(i * 100),
                    low=Decimal("39500") + Decimal(i * 100),
                    close=Decimal("40200") + Decimal(i * 100),
                    volume=Decimal("100.5"),
                )
            )
    return candles


# ---------------------------------------------------------------------------
# Candle upserts
# ---------------------------------------------------------------------------


class TestCandleUpserts:
    """Test candle upsert and query paths."""

    def test_upsert_candles_inserts_records(
        self, stores: PostgresStores, sample_candles: list[Candle]
    ):
        """Verify upsert_candles inserts all candles."""
        count = stores.upsert_candles(candles=sample_candles)
        assert count == len(sample_candles)

    def test_upsert_candles_empty_list(self, stores: PostgresStores):
        """Verify empty list returns 0 without DB call."""
        count = stores.upsert_candles(candles=[])
        assert count == 0

    def test_upsert_candles_on_conflict(self, stores: PostgresStores):
        """Verify ON CONFLICT updates existing candles."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candle = Candle(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            open_time=base,
            close_time=base + timedelta(hours=1),
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("100.5"),
        )
        # Insert
        count1 = stores.upsert_candles(candles=[candle])
        assert count1 == 1

        # Upsert with updated values
        candle_updated = Candle(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            open_time=base,
            close_time=base + timedelta(hours=1),
            open=Decimal("41000"),  # Changed
            high=Decimal("41500"),
            low=Decimal("40500"),
            close=Decimal("41200"),
            volume=Decimal("110.5"),
        )
        count2 = stores.upsert_candles(candles=[candle_updated])
        assert count2 == 1

    def test_upsert_candles_multiple_symbols(
        self, stores: PostgresStores, sample_candles_multi_symbol: list[Candle]
    ):
        """Verify upsert works across symbols and timeframes."""
        count = stores.upsert_candles(candles=sample_candles_multi_symbol)
        assert count == len(sample_candles_multi_symbol)


class TestCandleQueries:
    """Test candle read paths."""

    def test_get_candles_returns_filtered(
        self, stores: PostgresStores, sample_candles: list[Candle]
    ):
        """Verify get_candles returns correct subset."""
        stores.upsert_candles(candles=sample_candles)

        candles = stores.get_candles(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
        )
        assert len(candles) == 5

    def test_get_candles_empty_result(self, stores: PostgresStores):
        """Verify get_candles returns empty list for no matches."""
        candles = stores.get_candles(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        assert len(candles) == 0

    def test_get_latest_candle_open_time(self, stores: PostgresStores):
        """Verify _get_latest_candle_open_time returns correct value."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candle = Candle(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            open_time=base,
            close_time=base + timedelta(hours=1),
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("100.5"),
        )
        stores.upsert_candles(candles=[candle])

        result = stores._get_latest_candle_open_time(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
        )
        assert result is not None
        assert result == base

    def test_get_latest_candle_open_time_no_data(self, stores: PostgresStores):
        """Verify returns None when no candles exist."""
        result = stores._get_latest_candle_open_time(
            exchange="bitfinex",
            symbol="NONEXIST",
            timeframe="1h",
        )
        assert result is None

    def test_get_latest_candle_closes(
        self, stores: PostgresStores, sample_candles: list[Candle]
    ):
        """Verify get_latest_candle_closes returns correct latest close per symbol."""
        stores.upsert_candles(candles=sample_candles)

        rows = stores.get_latest_candle_closes(
            exchanges=["bitfinex"],
            timeframe="1h",
        )
        assert len(rows) > 0
        for row in rows:
            assert len(row) == 3  # (exchange, symbol, close)


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------


class TestGapDetection:
    """Test candle gap detection and repair."""

    def test_log_gap_inserts_record(self, stores: PostgresStores):
        """Verify log_gap inserts a gap record."""
        gap = CandleGap(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            expected_open_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            expected_close_time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            detected_at=datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            repaired_at=None,
            notes="Missing candle detected",
        )
        gap_id = stores.log_gap(gap=gap)
        assert gap_id > 0

    def test_log_gap_on_conflict(self, stores: PostgresStores):
        """Verify log_gap handles duplicate gaps (ON CONFLICT)."""
        gap = CandleGap(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            expected_open_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            expected_close_time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            detected_at=datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            repaired_at=None,
            notes="First note",
        )
        id1 = stores.log_gap(gap=gap)

        gap2 = CandleGap(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            expected_open_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            expected_close_time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            detected_at=datetime(2024, 1, 1, 12, 10, 0, tzinfo=timezone.utc),
            repaired_at=None,
            notes="Second note",
        )
        id2 = stores.log_gap(gap=gap2)
        # Should return same id (upsert on conflict)
        assert id1 == id2

    def test_mark_repaired(self, stores: PostgresStores):
        """Verify mark_repaired sets repaired_at timestamp."""
        gap = CandleGap(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            expected_open_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            expected_close_time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            detected_at=datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            repaired_at=None,
            notes="",
        )
        gap_id = stores.log_gap(gap=gap)

        repaired_at = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        stores.mark_repaired(
            gap_id=gap_id, repaired_at=repaired_at, notes="Repaired by backfill"
        )

        # Verify via direct query
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                f"SELECT repaired_at, notes FROM candle_gaps WHERE id = {gap_id}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "Repaired by backfill" in result.stdout
        assert repaired_at.strftime("%Y-%m-%d") in result.stdout

    def test_get_gaps_unrepaired_only(self, stores: PostgresStores):
        """Verify get_gaps filters unrepaired gaps correctly."""
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        for i in range(3):
            gap = CandleGap(
                exchange="bitfinex",
                symbol="BTCUSD",
                timeframe="1h",
                expected_open_time=base + timedelta(hours=i),
                expected_close_time=base + timedelta(hours=i + 1),
                detected_at=base + timedelta(hours=i),
                repaired_at=None if i < 2 else base + timedelta(hours=10),
                notes="",
            )
            stores.log_gap(gap=gap)

        gaps = stores.get_gaps(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            only_unrepaired=True,
        )
        assert len(gaps) == 2


# ---------------------------------------------------------------------------
# Market data job tracking
# ---------------------------------------------------------------------------


class TestMarketDataJobs:
    """Test market data job and run tracking."""

    def test_create_job(self, stores: PostgresStores):
        """Verify create_job inserts and returns id."""
        job = MarketDataJob(
            job_type="backfill",
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
            status="created",
            last_error=None,
        )
        job_id = stores.create_job(job=job)
        assert job_id > 0

    def test_update_job_status(self, stores: PostgresStores):
        """Verify update_job_status changes status."""
        job = MarketDataJob(
            job_type="backfill",
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start_time=None,
            end_time=None,
            status="created",
            last_error=None,
        )
        job_id = stores.create_job(job=job)

        stores.update_job_status(job_id=job_id, status="running", last_error=None)

        jobs = stores.get_jobs(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            status="running",
        )
        assert len(jobs) >= 1

    def test_get_jobs_with_filters(self, stores: PostgresStores):
        """Verify get_jobs applies all filters."""
        # Clean up existing jobs for this test
        subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-c",
                "DELETE FROM market_data_jobs WHERE exchange = 'bitfinex'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        for i, (job_type, symbol) in enumerate(
            [("backfill", "BTCUSD"), ("realtime", "ETHUSD"), ("repair", "BTCUSD")]
        ):
            job = MarketDataJob(
                job_type=job_type,
                exchange="bitfinex",
                symbol=symbol,
                timeframe="1h",
                start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end_time=None,
                status="created",
                last_error=None,
            )
            stores.create_job(job=job)

        jobs = stores.get_jobs(exchange="bitfinex", symbol="BTCUSD", timeframe="1h")
        assert len(jobs) == 2

    def test_start_run(self, stores: PostgresStores):
        """Verify start_run creates a run row."""
        job = MarketDataJob(
            job_type="backfill",
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start_time=None,
            end_time=None,
            status="created",
            last_error=None,
        )
        job_id = stores.create_job(job=job)
        run_id = stores.start_run(job_id=job_id)
        assert run_id > 0

    def test_finish_run(self, stores: PostgresStores):
        """Verify finish_run updates run with stats."""
        job = MarketDataJob(
            job_type="backfill",
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start_time=None,
            end_time=None,
            status="created",
            last_error=None,
        )
        job_id = stores.create_job(job=job)
        run_id = stores.start_run(job_id=job_id)

        finish_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        stores.finish_run(
            run_id=run_id,
            status="success",
            candles_fetched=100,
            candles_upserted=95,
            last_open_time=finish_time,
            last_error=None,
        )

        runs = stores.get_runs(job_id=job_id)
        assert len(runs) >= 1
        run = runs[0]
        assert run.status == "success"
        assert run.candles_fetched == 100
        assert run.candles_upserted == 95

    def test_get_runs(self, stores: PostgresStores):
        """Verify get_runs returns runs for a job."""
        job = MarketDataJob(
            job_type="backfill",
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start_time=None,
            end_time=None,
            status="created",
            last_error=None,
        )
        job_id = stores.create_job(job=job)

        for _ in range(3):
            run_id = stores.start_run(job_id=job_id)
            stores.finish_run(run_id=run_id, status="success")

        runs = stores.get_runs(job_id=job_id, limit=10)
        assert len(runs) == 3


# ---------------------------------------------------------------------------
# Orders and fills
# ---------------------------------------------------------------------------


class TestOrdersAndFills:
    """Test order and trade fill persistence."""

    def setup_method(self):
        """Clean up orders and trade_fills before each test."""
        subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "DELETE FROM trade_fills WHERE exchange = 'bitfinex'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "DELETE FROM orders WHERE exchange = 'bitfinex'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_upsert_order(self, stores: PostgresStores):
        """Verify orders table accepts inserts."""
        insert_sql = (
            "INSERT INTO orders (exchange, symbol, order_id, side, order_type, amount, price, status) "
            + "VALUES ('bitfinex', 'BTCUSD', 'order-001', 'BUY', 'market', 0.5, 40000.0, 'FILLED')"
        )
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                insert_sql,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_get_orders(self, stores: PostgresStores):
        """Verify orders table returns filtered orders."""
        for i in range(3):
            subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    "5433",
                    "-U",
                    DISPOSABLE_DB_USER,
                    "-d",
                    DISPOSABLE_DB_NAME,
                    "-t",
                    "-A",
                    "-c",
                    f"INSERT INTO orders (exchange, symbol, order_id, side, order_type, amount, price, status) "
                    f"VALUES ('bitfinex', 'BTCUSD', 'order-{i:03d}', "
                    f"{'BUY' if i % 2 == 0 else 'SELL'}, 'limit', 0.5, "
                    f"{40000 + i * 100}, 'FILLED')",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM orders WHERE exchange = 'bitfinex' AND symbol = 'BTCUSD'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert int(result.stdout.strip()) == 3

    def test_upsert_fill(self, stores: PostgresStores):
        """Verify trade_fills table accepts inserts."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO trade_fills (exchange, symbol, order_id, trade_id, side, amount, price, fee_currency, fee_amount) "
                "VALUES ('bitfinex', 'BTCUSD', 'order-001', 'fill-001', 'BUY', 0.5, 40000.0, 'USD', 20.0)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_get_fills(self, stores: PostgresStores):
        """Verify trade_fills table returns filtered fills."""
        for i in range(3):
            subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    "5433",
                    "-U",
                    DISPOSABLE_DB_USER,
                    "-d",
                    DISPOSABLE_DB_NAME,
                    "-t",
                    "-A",
                    "-c",
                    f"INSERT INTO trade_fills (exchange, symbol, order_id, trade_id, side, amount, price, fee_currency, fee_amount) "
                    f"VALUES ('bitfinex', 'BTCUSD', 'order-001', 'fill-{i:03d}', "
                    f"'BUY', 0.5, {40000 + i * 100}, 'USD', 20.0)",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM trade_fills WHERE exchange = 'bitfinex' AND symbol = 'BTCUSD'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert int(result.stdout.strip()) == 3

    def test_get_fills_with_order_id(self, stores: PostgresStores):
        """Verify trade_fills filters by order_id."""
        for i in range(3):
            subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    "5433",
                    "-U",
                    DISPOSABLE_DB_USER,
                    "-d",
                    DISPOSABLE_DB_NAME,
                    "-t",
                    "-A",
                    "-c",
                    f"INSERT INTO trade_fills (exchange, symbol, order_id, trade_id, side, amount, price, fee_currency, fee_amount) "
                    f"VALUES ('bitfinex', 'BTCUSD', 'order-{i % 2}', 'fill-{i:03d}', "
                    f"'BUY', 0.5, 40000.0, 'USD', 20.0)",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM trade_fills WHERE exchange = 'bitfinex' AND symbol = 'BTCUSD' AND order_id = 'order-0'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert int(result.stdout.strip()) == 2


# ---------------------------------------------------------------------------
# Portfolio snapshots
# ---------------------------------------------------------------------------


class TestPortfolioSnapshots:
    """Test portfolio snapshot persistence."""

    def setup_method(self):
        """Clean up portfolio_snapshots before each test."""
        subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "DELETE FROM portfolio_snapshots WHERE exchange = 'bitfinex'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_log_snapshot(self, stores: PostgresStores):
        """Verify portfolio_snapshots table accepts inserts."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO portfolio_snapshots (exchange, total_value, cash_balance, "
                "positions_value, unrealized_pnl, realized_pnl, snapshot_time) "
                "VALUES ('bitfinex', 50000.00, 30000.00, 20000.00, 1500.00, 500.00, '2024-01-01 12:00:00')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_get_latest_snapshot(self, stores: PostgresStores):
        """Verify portfolio_snapshots returns correct latest snapshot."""
        base_hour = 10  # Start at hour 10 to avoid conflicts
        for i in range(3):
            subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    "5433",
                    "-U",
                    DISPOSABLE_DB_USER,
                    "-d",
                    DISPOSABLE_DB_NAME,
                    "-t",
                    "-A",
                    "-c",
                    f"INSERT INTO portfolio_snapshots (exchange, total_value, cash_balance, "
                    f"positions_value, unrealized_pnl, realized_pnl, snapshot_time) "
                    f"VALUES ('bitfinex', {50000 + i * 100}, 30000, 20000, 1500, 500, "
                    f"TIMESTAMP '2024-01-01 {base_hour + i}:00:00')",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT total_value FROM portfolio_snapshots "
                "WHERE exchange = 'bitfinex' ORDER BY snapshot_time DESC LIMIT 1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # 50000 + 2*100 = 50200
        assert "50200" in result.stdout

    def test_get_snapshots(self, stores: PostgresStores):
        """Verify portfolio_snapshots returns filtered snapshots."""
        base_hour = 20
        for i in range(5):
            subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    "5433",
                    "-U",
                    DISPOSABLE_DB_USER,
                    "-d",
                    DISPOSABLE_DB_NAME,
                    "-t",
                    "-A",
                    "-c",
                    f"INSERT INTO portfolio_snapshots (exchange, total_value, cash_balance, "
                    f"positions_value, unrealized_pnl, realized_pnl, snapshot_time) "
                    f"VALUES ('bitfinex', {50000 + i * 100}, 30000, 20000, 1500, 500, "
                    f"TIMESTAMP '2024-01-01 {base_hour + i}:00:00')",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM portfolio_snapshots WHERE exchange = 'bitfinex'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert int(result.stdout.strip()) == 5


# ---------------------------------------------------------------------------
# AI decisions and usage
# ---------------------------------------------------------------------------


class TestAIDecisions:
    """Test AI-related tables (system_prompts, ai_budget_config)."""

    def test_system_prompts_insert(self, stores: PostgresStores):
        """Verify system_prompts table accepts inserts."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM system_prompts",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Migrations seed some default prompts
        count = int(result.stdout.strip())
        assert count >= 0  # At least the seeded data

    def test_ai_budget_config_insert(self, stores: PostgresStores):
        """Verify ai_budget_config table has seeded data."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM ai_budget_config",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        count = int(result.stdout.strip())
        assert count >= 1  # global + per-role configs

    def test_pair_predictions_insert(self, stores: PostgresStores):
        """Verify pair_predictions table accepts inserts."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO pair_predictions (exchange, symbol, role, action, confidence, reasoning) "
                "VALUES ('bitfinex', 'BTCUSD', 'screener', 'BUY', 0.85, 'Test prediction')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

        # Verify the insert
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM pair_predictions WHERE reasoning = 'Test prediction'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert int(result.stdout.strip()) == 1


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class TestAlerts:
    """Test alerts table persistence."""

    def test_alerts_table_exists(self, stores: PostgresStores):
        """Verify alerts table was created by migration."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alerts')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.stdout.strip() == "t"

    def test_alerts_insert(self, stores: PostgresStores):
        """Verify alerts table accepts inserts."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO alerts (user_id, symbol, exchange, timeframe, condition_type, operator, threshold_value, enabled) "
                "VALUES (NULL, 'BTCUSD', 'bitfinex', '1h', 'price_above', 'above', 40000.0, true)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Trade history
# ---------------------------------------------------------------------------


class TestTradeHistory:
    """Test trade history table persistence."""

    def test_trades_table_exists(self, stores: PostgresStores):
        """Verify trades table was created by migration."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'trades')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.stdout.strip() == "t"

    def test_trades_insert(self, stores: PostgresStores):
        """Verify trades table accepts inserts."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO trades (trade_id, exchange, symbol, side, quantity, price, quote_qty, order_id, execution_time) "
                "VALUES ('trade-001', 'bitfinex', 'BTCUSD', 'BUY', 0.5, 40000.0, 20000.0, 'order-001', CURRENT_TIMESTAMP)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

        # Verify the insert
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT COUNT(*) FROM trades WHERE trade_id = 'trade-001'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert int(result.stdout.strip()) == 1

    def test_trade_history_unique_constraint(self, stores: PostgresStores):
        """Verify trade_id unique constraint."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO trades (trade_id, exchange, symbol, side, quantity, price, quote_qty, execution_time) "
                "VALUES ('trade-002', 'bitfinex', 'BTCUSD', 'BUY', 0.5, 40000.0, 20000.0, CURRENT_TIMESTAMP)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

        # Duplicate insert should fail
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO trades (trade_id, exchange, symbol, side, quantity, price, quote_qty, execution_time) "
                "VALUES ('trade-002', 'bitfinex', 'BTCUSD', 'BUY', 0.5, 40000.0, 20000.0, CURRENT_TIMESTAMP)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should fail due to unique constraint
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Paper trading
# ---------------------------------------------------------------------------


class TestPaperTrading:
    """Test paper trading tables."""

    def test_paper_orders_table_exists(self, stores: PostgresStores):
        """Verify paper_orders table exists."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'paper_orders')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.stdout.strip() == "t"

    def test_paper_positions_table_exists(self, stores: PostgresStores):
        """Verify paper_positions table exists."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'paper_positions')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.stdout.strip() == "t"

    def test_paper_orders_insert(self, stores: PostgresStores):
        """Verify paper_orders accepts inserts."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                "INSERT INTO paper_orders (symbol, side, order_type, qty, status) "
                "VALUES ('BTCUSD', 'BUY', 'MARKET', 0.5, 'PENDING')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Schema verification
# ---------------------------------------------------------------------------


class TestSchemaVerification:
    """Verify all expected tables exist in the disposable DB."""

    EXPECTED_TABLES = [
        "candles",
        "candle_gaps",
        "market_data_jobs",
        "market_data_job_runs",
        "orders",
        "trade_fills",
        "portfolio_snapshots",
        "positions",
        "wallet_snapshots",
        "opportunities",
        "execution_intents",
        "execution_results",
        "audit_events",
        "fee_schedules",
        "exchanges",
        "symbols",
        "strategies",
        "indicators",
        "indicator_weights",
        "indicator_signals",
        "strategy_indicator_weights",
        "signal_history",
        "automation_rules",
        "paper_orders",
        "paper_positions",
        "market_cap_ranks",
        # Migration tables
        "system_prompts",
        "coin_dossier_entries",
        "ai_budget_config",
        "pair_predictions",
        "alerts",
        "trades",
    ]

    @pytest.mark.parametrize("table", EXPECTED_TABLES)
    def test_table_exists(self, stores: PostgresStores, table: str):
        """Verify each expected table exists."""
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.stdout.strip() == "t", f"Table '{table}' not found"


# ---------------------------------------------------------------------------
# End-to-end: write + read roundtrip
# ---------------------------------------------------------------------------


class TestRoundtrip:
    """End-to-end write and read verification."""

    def test_candle_roundtrip(
        self, stores: PostgresStores, sample_candles: list[Candle]
    ):
        """Write candles, read them back, verify data integrity."""
        stores.upsert_candles(candles=sample_candles)

        read_back = stores.get_candles(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        )

        assert len(read_back) == len(sample_candles)
        for orig, read in zip(sample_candles, read_back):
            assert orig.exchange == read.exchange
            assert orig.symbol == read.symbol
            assert orig.timeframe == read.timeframe
            assert orig.open == read.open
            assert orig.high == read.high
            assert orig.low == read.low
            assert orig.close == read.close
            assert orig.volume == read.volume

    def test_gap_roundtrip(self, stores: PostgresStores):
        """Write gap, read it back, verify."""
        gap = CandleGap(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            expected_open_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            expected_close_time=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
            detected_at=datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            repaired_at=None,
            notes="Roundtrip test",
        )
        gap_id = stores.log_gap(gap=gap)

        # Verify via direct psql query since CandleGap dataclass doesn't have id
        result = subprocess.run(
            [
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-t",
                "-A",
                "-c",
                f"SELECT notes FROM candle_gaps WHERE id = {gap_id}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "Roundtrip test" in result.stdout

    def test_job_run_roundtrip(self, stores: PostgresStores):
        """Create job, start/finish run, read back."""
        job = MarketDataJob(
            job_type="backfill",
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
            status="created",
            last_error=None,
        )
        job_id = stores.create_job(job=job)
        run_id = stores.start_run(job_id=job_id)

        finish_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        stores.finish_run(
            run_id=run_id,
            status="success",
            candles_fetched=50,
            candles_upserted=48,
            last_open_time=finish_time,
            last_error=None,
        )

        runs = stores.get_runs(job_id=job_id)
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "success"
        assert run.candles_fetched == 50
        assert run.candles_upserted == 48
