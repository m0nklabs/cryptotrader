from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data.bitfinex_gap_repair import (
    _align_to_step,
    _to_ms,
    _find_missing_open_times,
)
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores


def test_align_to_step_1m():
    """Test aligning datetime to 1-minute step."""
    dt = datetime(2024, 1, 1, 12, 34, 56, tzinfo=timezone.utc)
    aligned = _align_to_step(dt, step_seconds=60)
    assert aligned == datetime(2024, 1, 1, 12, 34, 0, tzinfo=timezone.utc)


def test_align_to_step_5m():
    """Test aligning datetime to 5-minute step."""
    dt = datetime(2024, 1, 1, 12, 37, 45, tzinfo=timezone.utc)
    aligned = _align_to_step(dt, step_seconds=300)
    assert aligned == datetime(2024, 1, 1, 12, 35, 0, tzinfo=timezone.utc)


def test_align_to_step_1h():
    """Test aligning datetime to 1-hour step."""
    dt = datetime(2024, 1, 1, 12, 37, 45, tzinfo=timezone.utc)
    aligned = _align_to_step(dt, step_seconds=3600)
    assert aligned == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_align_to_step_handles_naive_datetime():
    """Test that align_to_step converts naive datetime to UTC."""
    dt = datetime(2024, 1, 1, 12, 34, 56)  # naive
    aligned = _align_to_step(dt, step_seconds=60)
    assert aligned.tzinfo == timezone.utc
    assert aligned == datetime(2024, 1, 1, 12, 34, 0, tzinfo=timezone.utc)


def test_to_ms_converts_correctly():
    """Test datetime to milliseconds conversion."""
    dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    ms = _to_ms(dt)
    assert ms == 1704067200000


def test_to_ms_handles_naive_datetime():
    """Test that to_ms treats naive datetime as UTC."""
    dt = datetime(2024, 1, 1, 0, 0, 0)  # naive
    ms = _to_ms(dt)
    assert ms == 1704067200000


@pytest.fixture
def mock_stores(monkeypatch):
    """Create a mocked PostgresStores instance for gap detection tests."""
    config = PostgresConfig(database_url="postgresql://test:test@localhost/test")
    stores = PostgresStores(config=config)
    
    # Mock engine and SQLAlchemy
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_engine.begin.return_value.__exit__.return_value = None
    
    monkeypatch.setattr(stores, "_get_engine", lambda: mock_engine)
    monkeypatch.setattr(stores, "_require_sqlalchemy", lambda: (MagicMock(), MagicMock()))
    
    return stores, mock_conn


def test_find_missing_open_times_detects_gaps(mock_stores):
    """Test that gap detection identifies missing candles."""
    stores, mock_conn = mock_stores
    
    # Mock the database query to return missing times
    missing_time1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    missing_time2 = datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc)
    
    mock_conn.execute.return_value.fetchall.return_value = [
        (missing_time1,),
        (missing_time2,),
    ]
    
    result = _find_missing_open_times(
        stores=stores,
        exchange="bitfinex",
        symbol="BTCUSD",
        timeframe="1m",
        start=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
    )
    
    assert len(result) == 2
    assert result[0] == missing_time1
    assert result[1] == missing_time2


def test_find_missing_open_times_no_gaps(mock_stores):
    """Test that gap detection returns empty list when no gaps exist."""
    stores, mock_conn = mock_stores
    
    # Mock the database query to return no missing times
    mock_conn.execute.return_value.fetchall.return_value = []
    
    result = _find_missing_open_times(
        stores=stores,
        exchange="bitfinex",
        symbol="BTCUSD",
        timeframe="1m",
        start=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
    )
    
    assert len(result) == 0


def test_find_missing_open_times_raises_for_invalid_timeframe(mock_stores):
    """Test that gap detection raises error for unsupported timeframe."""
    stores, _ = mock_stores
    
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        _find_missing_open_times(
            stores=stores,
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="30m",  # unsupported
            start=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
        )
