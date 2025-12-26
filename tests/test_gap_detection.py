"""Tests for gap detection algorithm.

Tests the gap detection logic that identifies missing candles in time series data.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data.bitfinex_gap_repair import _find_missing_open_times, _align_to_step
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores


def test_align_to_step_aligns_to_hour_boundary() -> None:
    """Verify _align_to_step correctly aligns datetime to hourly boundaries."""
    dt = datetime(2024, 1, 1, 12, 30, 45, tzinfo=timezone.utc)
    aligned = _align_to_step(dt, step_seconds=3600)

    assert aligned == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_align_to_step_aligns_to_5min_boundary() -> None:
    """Verify _align_to_step correctly aligns datetime to 5-minute boundaries."""
    dt = datetime(2024, 1, 1, 12, 33, 45, tzinfo=timezone.utc)
    aligned = _align_to_step(dt, step_seconds=300)  # 5 minutes

    assert aligned == datetime(2024, 1, 1, 12, 30, 0, tzinfo=timezone.utc)


def test_align_to_step_handles_naive_datetime() -> None:
    """Verify _align_to_step adds UTC timezone to naive datetimes."""
    dt = datetime(2024, 1, 1, 12, 30, 45)  # Naive
    aligned = _align_to_step(dt, step_seconds=3600)

    assert aligned.tzinfo is not None
    assert aligned.tzinfo == timezone.utc
    assert aligned == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "step_seconds,input_hour,expected_hour",
    [
        (3600, 13, 13),  # 1h boundary - aligns to current hour
        (14400, 13, 12),  # 4h boundary - aligns to nearest 4h mark (12)
        (86400, 13, 0),  # 1d boundary (midnight)
    ],
)
def test_align_to_step_various_timeframes(step_seconds: int, input_hour: int, expected_hour: int) -> None:
    """Verify _align_to_step works correctly for various timeframes."""
    dt = datetime(2024, 1, 1, input_hour, 30, 45, tzinfo=timezone.utc)
    aligned = _align_to_step(dt, step_seconds=step_seconds)

    assert aligned.hour == expected_hour
    assert aligned.minute == 0
    assert aligned.second == 0


def test_find_missing_open_times_detects_single_gap() -> None:
    """Verify _find_missing_open_times detects a single missing candle."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    # Setup: We expect candles at hours 0, 1, 2, 3, 4
    # But only 0, 1, 3, 4 exist in DB (hour 2 is missing)
    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 4, 0, 0, tzinfo=timezone.utc)

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()

    # Return missing hour 2
    missing_time = datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
    mock_result.fetchall.return_value = [(missing_time,)]
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        missing = _find_missing_open_times(
            stores=stores,
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start=start,
            end=end,
        )

    assert len(missing) == 1
    assert missing[0] == missing_time


def test_find_missing_open_times_detects_multiple_gaps() -> None:
    """Verify _find_missing_open_times detects multiple missing candles."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()

    # Return missing hours 2, 5, 7
    missing_times = [
        (datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc),),
        (datetime(2024, 1, 1, 5, 0, 0, tzinfo=timezone.utc),),
        (datetime(2024, 1, 1, 7, 0, 0, tzinfo=timezone.utc),),
    ]
    mock_result.fetchall.return_value = missing_times
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        missing = _find_missing_open_times(
            stores=stores,
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start=start,
            end=end,
        )

    assert len(missing) == 3
    assert missing[0] == datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
    assert missing[1] == datetime(2024, 1, 1, 5, 0, 0, tzinfo=timezone.utc)
    assert missing[2] == datetime(2024, 1, 1, 7, 0, 0, tzinfo=timezone.utc)


def test_find_missing_open_times_returns_empty_when_no_gaps() -> None:
    """Verify _find_missing_open_times returns empty list when no gaps exist."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 5, 0, 0, tzinfo=timezone.utc)

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.fetchall.return_value = []  # No missing candles
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        missing = _find_missing_open_times(
            stores=stores,
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start=start,
            end=end,
        )

    assert len(missing) == 0
    assert missing == []


def test_find_missing_open_times_uses_correct_step_for_timeframe() -> None:
    """Verify _find_missing_open_times uses correct step_seconds for different timeframes."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 4, 0, 0, tzinfo=timezone.utc)

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.fetchall.return_value = []
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        _find_missing_open_times(
            stores=stores,
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="4h",  # 4-hour timeframe
            start=start,
            end=end,
        )

    # Verify the execute was called with correct step_seconds for 4h timeframe
    assert mock_conn.execute.called
    call_args = mock_conn.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params["step_seconds"] == 14400  # 4 hours in seconds


def test_find_missing_open_times_handles_consecutive_gaps() -> None:
    """Verify _find_missing_open_times correctly identifies consecutive missing candles."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()

    # Consecutive missing hours: 3, 4, 5, 6
    missing_times = [
        (datetime(2024, 1, 1, 3, 0, 0, tzinfo=timezone.utc),),
        (datetime(2024, 1, 1, 4, 0, 0, tzinfo=timezone.utc),),
        (datetime(2024, 1, 1, 5, 0, 0, tzinfo=timezone.utc),),
        (datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc),),
    ]
    mock_result.fetchall.return_value = missing_times
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        missing = _find_missing_open_times(
            stores=stores,
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            start=start,
            end=end,
        )

    assert len(missing) == 4
    # Verify they are consecutive
    for i in range(len(missing) - 1):
        assert (missing[i + 1] - missing[i]) == timedelta(hours=1)
