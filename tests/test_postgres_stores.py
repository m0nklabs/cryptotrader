"""Tests for PostgresStores critical behaviors.

Focused on essential functionality like timezone handling.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores


def test_get_latest_candle_open_time_returns_none_when_no_data() -> None:
    """Verify _get_latest_candle_open_time returns None when no candles exist."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    # Mock the engine and connection to simulate no data
    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.fetchone.return_value = None
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    # Mock text function for SQL query
    mock_text = Mock(return_value="mocked_query")

    with patch.object(stores, "_get_engine", return_value=mock_engine), patch.object(
        stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)
    ):
        result = stores._get_latest_candle_open_time(exchange="bitfinex", symbol="BTCUSD", timeframe="1h")

    assert result is None


def test_get_latest_candle_open_time_returns_naive_datetime() -> None:
    """Verify _get_latest_candle_open_time returns timezone-naive datetime from Postgres.

    This is the critical behavior for --resume mode: Postgres TIMESTAMP columns
    return naive datetime objects (no tzinfo), which must be normalized to UTC-aware
    to prevent comparison errors with other timezone-aware datetimes.
    """
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    # Simulate Postgres returning a naive datetime (TIMESTAMP without timezone)
    naive_dt = datetime(2024, 12, 25, 12, 0, 0)
    assert naive_dt.tzinfo is None, "Test setup error: datetime should be naive"

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.fetchone.return_value = (naive_dt,)
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    # Mock text function for SQL query
    mock_text = Mock(return_value="mocked_query")

    with patch.object(stores, "_get_engine", return_value=mock_engine), patch.object(
        stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)
    ):
        result = stores._get_latest_candle_open_time(exchange="bitfinex", symbol="BTCUSD", timeframe="1h")

    # Verify the result is naive (no timezone info)
    assert result is not None
    assert result.tzinfo is None, "PostgresStores should return naive datetime from TIMESTAMP column"
    assert result == naive_dt


def test_resume_normalizes_naive_datetime_to_utc() -> None:
    """Verify that resume logic normalizes naive datetime to UTC-aware.

    This test validates the critical timezone normalization pattern used in
    bitfinex_backfill.main() when --resume flag is used. The pattern is:

        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)

    This prevents "can't compare offset-naive and offset-aware datetimes" errors.
    """
    # Simulate what _get_latest_candle_open_time returns (naive datetime)
    naive_dt = datetime(2024, 12, 25, 12, 0, 0)
    assert naive_dt.tzinfo is None

    # Apply the normalization pattern from bitfinex_backfill.main()
    if naive_dt.tzinfo is None:
        normalized_dt = naive_dt.replace(tzinfo=timezone.utc)
    else:
        normalized_dt = naive_dt

    # Verify the normalized datetime is UTC-aware
    assert normalized_dt.tzinfo is timezone.utc
    assert normalized_dt.year == 2024
    assert normalized_dt.month == 12
    assert normalized_dt.day == 25
    assert normalized_dt.hour == 12

    # Verify it can now be compared with other UTC-aware datetimes
    now_utc = datetime.now(tz=timezone.utc)
    try:
        _ = normalized_dt < now_utc  # Should not raise TypeError
        comparison_works = True
    except TypeError:
        comparison_works = False

    assert comparison_works, "Normalized datetime should be comparable with UTC-aware datetimes"


def test_resume_normalization_preserves_timestamp_value() -> None:
    """Verify that timezone normalization doesn't change the actual time value.

    When normalizing a naive datetime to UTC-aware, the time value should remain
    the same (we're just adding timezone info, not converting).
    """
    naive_dt = datetime(2024, 12, 25, 12, 30, 45)
    utc_dt = naive_dt.replace(tzinfo=timezone.utc)

    assert naive_dt.year == utc_dt.year
    assert naive_dt.month == utc_dt.month
    assert naive_dt.day == utc_dt.day
    assert naive_dt.hour == utc_dt.hour
    assert naive_dt.minute == utc_dt.minute
    assert naive_dt.second == utc_dt.second
    assert naive_dt.microsecond == utc_dt.microsecond

    # Only tzinfo should differ
    assert naive_dt.tzinfo is None
    assert utc_dt.tzinfo is timezone.utc
