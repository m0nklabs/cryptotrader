"""Tests for portfolio API endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    conn = AsyncMock()

    # Mock context manager for pool.acquire()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None

    return pool, conn


def test_portfolio_snapshots_returns_results(mock_db_pool):
    """Test fetching portfolio snapshots."""
    pool, conn = mock_db_pool

    # Mock database response
    conn.fetch.return_value = [
        {
            "id": 1,
            "timestamp": datetime(2024, 1, 1, 12, 0, 0),
            "total_equity": Decimal("10000"),
            "cash_balance": Decimal("5000"),
            "position_value": Decimal("5000"),
            "unrealized_pnl": Decimal("500"),
            "realized_pnl": Decimal("300"),
            "total_pnl": Decimal("800"),
            "quote_currency": "USDT",
        }
    ]

    with patch("api.routes.portfolio._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/portfolio/snapshots?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert "snapshots" in payload
    assert len(payload["snapshots"]) == 1
    assert payload["snapshots"][0]["total_equity"] == "10000"


def test_portfolio_latest_snapshot_not_found():
    """Test fetching latest snapshot when none exists."""
    pool = AsyncMock()
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None

    with patch("api.routes.portfolio._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/portfolio/snapshots/latest")

    assert response.status_code == 404


def test_portfolio_position_history_with_symbol_filter(mock_db_pool):
    """Test fetching position history with symbol filter."""
    pool, conn = mock_db_pool

    conn.fetch.return_value = [
        {
            "id": 1,
            "timestamp": datetime(2024, 1, 1, 12, 0, 0),
            "symbol": "BTCUSD",
            "exchange": "bitfinex",
            "quantity": Decimal("0.5"),
            "avg_entry_price": Decimal("50000"),
            "current_price": Decimal("51000"),
            "unrealized_pnl": Decimal("500"),
            "realized_pnl": Decimal("0"),
            "cost_basis": "FIFO",
        }
    ]

    with patch("api.routes.portfolio._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/portfolio/positions/history?symbol=BTCUSD&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert "history" in payload
    assert len(payload["history"]) == 1
    assert payload["history"][0]["symbol"] == "BTCUSD"


def test_portfolio_balance_history(mock_db_pool):
    """Test fetching balance history."""
    pool, conn = mock_db_pool

    conn.fetch.return_value = [
        {
            "id": 1,
            "timestamp": datetime(2024, 1, 1, 12, 0, 0),
            "exchange": "bitfinex",
            "currency": "USD",
            "available": Decimal("5000"),
            "reserved": Decimal("1000"),
            "total": Decimal("6000"),
        }
    ]

    with patch("api.routes.portfolio._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/portfolio/balances/history?exchange=bitfinex&currency=USD")

    assert response.status_code == 200
    payload = response.json()
    assert "history" in payload
    assert len(payload["history"]) == 1
    assert payload["history"][0]["exchange"] == "bitfinex"
