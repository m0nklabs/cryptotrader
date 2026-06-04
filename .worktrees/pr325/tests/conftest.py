"""Shared test fixtures for pytest.

Provides common test data, mocks, and utilities used across multiple test files.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.types import Candle


@pytest.fixture
def sample_candles() -> list[Candle]:
    """Sample candles for testing.

    Returns a list of 5 consecutive 1h candles for BTCUSD on bitfinex.
    """
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
def api_client():
    """Provide a TestClient for API endpoint testing."""
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)
