"""Shared test fixtures for pytest.

Provides common test data, mocks, and utilities used across multiple test files.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pytest

from core.types import Candle


@pytest.fixture
def sample_candles() -> list[Candle]:
    """Sample candles for testing.

    Returns a list of 5 consecutive 1h candles for BTCUSD on bitfinex.
    """
    base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []

    for i in range(5):
        open_time = datetime(2024, 1, 1, i, 0, 0, tzinfo=timezone.utc)
        close_time = datetime(2024, 1, 1, i + 1, 0, 0, tzinfo=timezone.utc)
        candles.append(
            Candle(
                exchange="bitfinex",
                symbol="BTCUSD",
                timeframe="1h",
                open_time=open_time,
                close_time=close_time,
                open=Decimal("40000") + Decimal(i * 100),
                high=Decimal("40500") + Decimal(i * 100),
                low=Decimal("39500") + Decimal(i * 100),
                close=Decimal("40200") + Decimal(i * 100),
                volume=Decimal("100.5"),
            )
        )

    return candles


@pytest.fixture
def mock_db_engine() -> Mock:
    """Mock SQLAlchemy engine for testing database operations."""
    mock_engine = Mock()
    mock_conn = Mock()
    mock_result = Mock()
    mock_result.rowcount = 1
    mock_result.fetchone.return_value = None
    mock_result.fetchall.return_value = []
    mock_conn.execute.return_value = mock_result
    mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = Mock(return_value=False)
    return mock_engine


@pytest.fixture
def mock_postgres_stores(mock_db_engine: Mock) -> Any:
    """Mock PostgresStores with a mocked database engine."""
    from unittest.mock import patch

    from core.storage.postgres.config import PostgresConfig
    from core.storage.postgres.stores import PostgresStores

    stores = PostgresStores(config=PostgresConfig(database_url="postgresql://fake"))

    with patch.object(stores, "_get_engine", return_value=mock_db_engine):
        yield stores
