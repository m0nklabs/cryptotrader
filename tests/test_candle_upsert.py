from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores
from core.types import Candle, Timeframe


@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine for testing."""
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    result.rowcount = 2
    conn.execute.return_value = result
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = None
    return engine


@pytest.fixture
def stores(monkeypatch, mock_engine):
    """Create a PostgresStores instance with mocked engine."""
    config = PostgresConfig(database_url="postgresql://test:test@localhost/test")
    stores = PostgresStores(config=config)
    
    # Mock the engine creation
    monkeypatch.setattr(stores, "_get_engine", lambda: mock_engine)
    
    # Mock the sqlalchemy imports
    def mock_require_sqlalchemy():
        return MagicMock(), MagicMock()
    
    monkeypatch.setattr(stores, "_require_sqlalchemy", mock_require_sqlalchemy)
    
    return stores


def test_upsert_candles_empty_list(stores):
    """Test that upserting an empty list returns 0."""
    result = stores.upsert_candles(candles=[])
    assert result == 0


def test_upsert_candles_single_candle(stores, mock_engine):
    """Test upserting a single candle."""
    candle = Candle(
        exchange="bitfinex",
        symbol="BTCUSD",
        timeframe="1m",
        open_time=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        close_time=datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc),
        open=Decimal("50000.00"),
        high=Decimal("50100.00"),
        low=Decimal("49900.00"),
        close=Decimal("50050.00"),
        volume=Decimal("10.5"),
    )
    
    result = stores.upsert_candles(candles=[candle])
    
    # Verify the engine was called
    assert mock_engine.begin.called
    
    # Verify the result
    assert result == 2


def test_upsert_candles_multiple_candles(stores, mock_engine):
    """Test upserting multiple candles."""
    candles = [
        Candle(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1m",
            open_time=datetime(2024, 1, 1, 0, i, tzinfo=timezone.utc),
            close_time=datetime(2024, 1, 1, 0, i + 1, tzinfo=timezone.utc),
            open=Decimal("50000.00"),
            high=Decimal("50100.00"),
            low=Decimal("49900.00"),
            close=Decimal("50050.00"),
            volume=Decimal("10.5"),
        )
        for i in range(5)
    ]
    
    # Mock rowcount for multiple candles
    conn = mock_engine.begin.return_value.__enter__.return_value
    conn.execute.return_value.rowcount = 5
    
    result = stores.upsert_candles(candles=candles)
    
    assert result == 5


def test_upsert_candles_formats_payload_correctly(stores, mock_engine):
    """Test that candle data is formatted correctly for database insertion."""
    candle = Candle(
        exchange="bitfinex",
        symbol="ETHUSD",
        timeframe="1h",
        open_time=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        close_time=datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc),
        open=Decimal("3000.00"),
        high=Decimal("3100.00"),
        low=Decimal("2900.00"),
        close=Decimal("3050.00"),
        volume=Decimal("100.0"),
    )
    
    stores.upsert_candles(candles=[candle])
    
    # Get the call arguments from the mock
    conn = mock_engine.begin.return_value.__enter__.return_value
    assert conn.execute.called
    
    # Verify execute was called with stmt and payload
    call_args = conn.execute.call_args
    assert call_args is not None
    # Second argument should be the payload list
    if len(call_args[0]) > 1:
        payload = call_args[0][1]
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["exchange"] == "bitfinex"
        assert payload[0]["symbol"] == "ETHUSD"
        assert payload[0]["timeframe"] == "1h"
