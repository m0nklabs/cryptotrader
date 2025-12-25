"""Tests for signal history logging."""

from __future__ import annotations

import json

import pytest

from core.signals.history import get_signal_history, log_signal_history


@pytest.mark.asyncio
async def test_log_signal_history_no_db():
    """Test log_signal_history returns False when no DB provided."""
    result = await log_signal_history(
        symbol="BTCUSD",
        timeframe="1h",
        score=75.0,
        indicator_contributions={"RSI": 20.0, "MACD": 30.0},
        db_pool=None,
    )
    assert result is False


@pytest.mark.asyncio
async def test_log_signal_history_with_mock_asyncpg():
    """Test log_signal_history with mocked asyncpg pool."""

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        def __init__(self):
            self.executed = False
            self.query = None
            self.params = None

        async def execute(self, query: str, *args):
            """Mock execute method."""
            self.executed = True
            self.query = query
            self.params = args

    mock_pool = MockAsyncPGPool()
    result = await log_signal_history(
        symbol="BTCUSD",
        timeframe="1h",
        score=75.5,
        indicator_contributions={"RSI": 20.0, "MACD": 30.0, "STOCH": 25.5},
        db_pool=mock_pool,
    )

    assert result is True
    assert mock_pool.executed is True
    assert "signal_history" in mock_pool.query
    assert mock_pool.params[0] == "BTCUSD"  # symbol
    assert mock_pool.params[1] == "1h"  # timeframe
    assert mock_pool.params[2] == 75.5  # score

    # Check contributions are JSON-encoded
    contributions_json = mock_pool.params[3]
    contributions = json.loads(contributions_json)
    assert contributions["RSI"] == 20.0
    assert contributions["MACD"] == 30.0
    assert contributions["STOCH"] == 25.5


@pytest.mark.asyncio
async def test_log_signal_history_db_error():
    """Test log_signal_history returns False on DB error."""

    class BrokenPool:
        """Mock pool that raises errors."""

        async def execute(self, query: str, *args):
            """Mock execute that raises error."""
            raise Exception("DB connection failed")

    broken_pool = BrokenPool()
    result = await log_signal_history(
        symbol="BTCUSD",
        timeframe="1h",
        score=75.0,
        indicator_contributions={"RSI": 20.0},
        db_pool=broken_pool,
    )

    # Should return False (silent failure)
    assert result is False


@pytest.mark.asyncio
async def test_log_signal_history_empty_contributions():
    """Test log_signal_history handles empty contributions."""

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        def __init__(self):
            self.executed = False
            self.params = None

        async def execute(self, query: str, *args):
            """Mock execute method."""
            self.executed = True
            self.params = args

    mock_pool = MockAsyncPGPool()
    result = await log_signal_history(
        symbol="ETHUSD",
        timeframe="15m",
        score=0.0,
        indicator_contributions={},
        db_pool=mock_pool,
    )

    assert result is True
    assert mock_pool.executed is True

    # Empty dict should be valid JSON
    contributions_json = mock_pool.params[3]
    contributions = json.loads(contributions_json)
    assert contributions == {}


@pytest.mark.asyncio
async def test_get_signal_history_no_db():
    """Test get_signal_history returns empty list when no DB provided."""
    history = await get_signal_history(db_pool=None)
    assert history == []


@pytest.mark.asyncio
async def test_get_signal_history_with_mock_asyncpg():
    """Test get_signal_history with mocked asyncpg pool."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        async def fetch(self, query: str, *args):
            """Mock fetch method."""
            # Return mock data
            return [
                {
                    "id": 1,
                    "symbol": "BTCUSD",
                    "timeframe": "1h",
                    "score": 75.5,
                    "indicator_contributions": '{"RSI": 20.0, "MACD": 30.0}',
                    "created_at": now,
                },
                {
                    "id": 2,
                    "symbol": "ETHUSD",
                    "timeframe": "1h",
                    "score": 60.0,
                    "indicator_contributions": '{"RSI": 30.0}',
                    "created_at": now,
                },
            ]

    mock_pool = MockAsyncPGPool()
    history = await get_signal_history(db_pool=mock_pool, limit=100)

    assert len(history) == 2
    assert history[0]["symbol"] == "BTCUSD"
    assert history[0]["score"] == 75.5
    assert history[1]["symbol"] == "ETHUSD"


@pytest.mark.asyncio
async def test_get_signal_history_with_filters():
    """Test get_signal_history applies filters correctly."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        def __init__(self):
            self.query = None
            self.params = None

        async def fetch(self, query: str, *args):
            """Mock fetch method."""
            self.query = query
            self.params = args
            return [
                {
                    "id": 1,
                    "symbol": "BTCUSD",
                    "timeframe": "1h",
                    "score": 75.5,
                    "indicator_contributions": "{}",
                    "created_at": now,
                }
            ]

    mock_pool = MockAsyncPGPool()
    history = await get_signal_history(
        symbol="BTCUSD",
        timeframe="1h",
        limit=50,
        db_pool=mock_pool,
    )

    assert len(history) == 1
    # Verify that parameters were passed
    assert "BTCUSD" in mock_pool.params
    assert "1h" in mock_pool.params


@pytest.mark.asyncio
async def test_get_signal_history_db_error():
    """Test get_signal_history returns empty list on DB error."""

    class BrokenPool:
        """Mock pool that raises errors."""

        async def fetch(self, query: str, *args):
            """Mock fetch that raises error."""
            raise Exception("DB connection failed")

    broken_pool = BrokenPool()
    history = await get_signal_history(db_pool=broken_pool)

    # Should return empty list (silent failure)
    assert history == []


@pytest.mark.asyncio
async def test_log_signal_history_special_characters():
    """Test log_signal_history handles special characters in symbol."""

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        def __init__(self):
            self.params = None

        async def execute(self, query: str, *args):
            """Mock execute method."""
            self.params = args

    mock_pool = MockAsyncPGPool()
    result = await log_signal_history(
        symbol="BTC/USD",  # Symbol with slash
        timeframe="1h",
        score=50.0,
        indicator_contributions={"test": 10.0},
        db_pool=mock_pool,
    )

    assert result is True
    assert mock_pool.params[0] == "BTC/USD"


@pytest.mark.asyncio
async def test_log_signal_history_high_precision_score():
    """Test log_signal_history handles high-precision scores."""

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        def __init__(self):
            self.params = None

        async def execute(self, query: str, *args):
            """Mock execute method."""
            self.params = args

    mock_pool = MockAsyncPGPool()
    result = await log_signal_history(
        symbol="BTCUSD",
        timeframe="1h",
        score=75.123456,  # High precision
        indicator_contributions={"RSI": 25.5, "MACD": 49.623456},
        db_pool=mock_pool,
    )

    assert result is True
    assert mock_pool.params[2] == 75.123456


@pytest.mark.asyncio
async def test_log_signal_history_many_indicators():
    """Test log_signal_history handles many indicator contributions."""

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        def __init__(self):
            self.params = None

        async def execute(self, query: str, *args):
            """Mock execute method."""
            self.params = args

    mock_pool = MockAsyncPGPool()

    # Create contributions for many indicators
    contributions = {f"IND_{i}": float(i * 10) for i in range(20)}

    result = await log_signal_history(
        symbol="BTCUSD",
        timeframe="1h",
        score=85.0,
        indicator_contributions=contributions,
        db_pool=mock_pool,
    )

    assert result is True

    # Verify all contributions are in JSON
    contributions_json = mock_pool.params[3]
    parsed = json.loads(contributions_json)
    assert len(parsed) == 20
    assert parsed["IND_0"] == 0.0
    assert parsed["IND_19"] == 190.0


@pytest.mark.asyncio
async def test_get_signal_history_limit():
    """Test get_signal_history respects limit parameter."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        def __init__(self):
            self.limit_used = None

        async def fetch(self, query: str, *args):
            """Mock fetch method."""
            # Extract limit from query or args
            self.limit_used = args[-1] if args else None
            # Return fake data
            return [
                {
                    "id": i,
                    "symbol": "BTCUSD",
                    "timeframe": "1h",
                    "score": 50.0,
                    "indicator_contributions": "{}",
                    "created_at": now,
                }
                for i in range(min(self.limit_used, 200))
            ]

    mock_pool = MockAsyncPGPool()

    # Test with custom limit
    history = await get_signal_history(db_pool=mock_pool, limit=25)

    assert mock_pool.limit_used == 25
    assert len(history) == 25
