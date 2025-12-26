"""Tests for candle upsert logic.

Tests the core candle insert/update functionality in PostgresStores.
Verifies that candles are properly inserted and updated when conflicts occur.
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

from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores
from core.types import Candle


@pytest.mark.parametrize(
    "candle_count,expected_upserted",
    [
        (0, 0),  # Empty list
        (1, 1),  # Single candle
        (5, 5),  # Multiple candles
        (100, 100),  # Large batch
    ],
)
def test_upsert_candles_returns_correct_count(
    candle_count: int,
    expected_upserted: int,
    sample_candles: list[Candle],
) -> None:
    """Verify upsert_candles returns the correct number of upserted records."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    # Create candles based on count
    if candle_count == 0:
        candles = []
    elif candle_count <= len(sample_candles):
        candles = sample_candles[:candle_count]
    else:
        # Extend sample_candles to reach the desired count using list comprehension
        base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = sample_candles.copy() + [
            Candle(
                exchange="bitfinex",
                symbol="BTCUSD",
                timeframe="1h",
                open_time=base + timedelta(hours=i),
                close_time=base + timedelta(hours=i + 1),
                open=Decimal("40000"),
                high=Decimal("40500"),
                low=Decimal("39500"),
                close=Decimal("40200"),
                volume=Decimal("100.5"),
            )
            for i in range(len(sample_candles), candle_count)
        ]

    # Mock the engine
    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.rowcount = expected_upserted
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        result = stores.upsert_candles(candles=candles)

    assert result == expected_upserted


def test_upsert_candles_handles_empty_list() -> None:
    """Verify upsert_candles returns 0 for empty candle list without DB call."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    # Should not call database at all for empty list
    with patch.object(stores, "_get_engine") as mock_get_engine:
        result = stores.upsert_candles(candles=[])

    assert result == 0
    mock_get_engine.assert_not_called()


def test_upsert_candles_constructs_correct_payload(sample_candles: list[Candle]) -> None:
    """Verify upsert_candles passes correctly formatted data to the database."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.rowcount = len(sample_candles)
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        stores.upsert_candles(candles=sample_candles)

    # Verify execute was called with correct payload structure
    assert mock_conn.execute.called

    # Extract the payload from the execute call: execute(statement, payload)
    execute_args, execute_kwargs = mock_conn.execute.call_args
    # We expect parameters to be passed positionally, not via kwargs
    assert not execute_kwargs
    assert len(execute_args) >= 2
    payload = execute_args[1]

    # Verify payload has correct structure
    assert len(payload) == len(sample_candles)
    for i, item in enumerate(payload):
        assert item["exchange"] == sample_candles[i].exchange
        assert item["symbol"] == sample_candles[i].symbol
        assert item["timeframe"] == str(sample_candles[i].timeframe)
        assert item["open_time"] == sample_candles[i].open_time
        assert item["close_time"] == sample_candles[i].close_time
        assert item["open"] == sample_candles[i].open
        assert item["high"] == sample_candles[i].high
        assert item["low"] == sample_candles[i].low
        assert item["close"] == sample_candles[i].close
        assert item["volume"] == sample_candles[i].volume


def test_upsert_candles_handles_conflict_with_update() -> None:
    """Verify upsert_candles correctly handles ON CONFLICT DO UPDATE scenario."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    # Create a candle
    candle = Candle(
        exchange="bitfinex",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        close_time=datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
        open=Decimal("40000"),
        high=Decimal("40500"),
        low=Decimal("39500"),
        close=Decimal("40200"),
        volume=Decimal("100.5"),
    )

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.rowcount = 1  # One row affected (insert or update)
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        result = stores.upsert_candles(candles=[candle])

    assert result == 1
    # Verify the SQL includes ON CONFLICT clause
    assert mock_text.called
    sql = mock_text.call_args[0][0]
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET" in sql


def test_upsert_candles_falls_back_to_payload_length_on_invalid_rowcount() -> None:
    """Verify upsert_candles falls back to payload length when rowcount is unreliable."""
    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    candles = [
        Candle(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            open_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            close_time=datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
            open=Decimal("40000"),
            high=Decimal("40500"),
            low=Decimal("39500"),
            close=Decimal("40200"),
            volume=Decimal("100.5"),
        )
    ]

    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    # Simulate unreliable rowcount (0 or None)
    mock_result.rowcount = 0
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

    mock_text = Mock(return_value="mocked_query")

    with (
        patch.object(stores, "_get_engine", return_value=mock_engine),
        patch.object(stores, "_require_sqlalchemy", return_value=(Mock(), mock_text)),
    ):
        result = stores.upsert_candles(candles=candles)

    # Should fall back to len(payload) = 1
    assert result == 1
