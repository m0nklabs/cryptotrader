"""Tests for trade history API endpoints."""

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
    
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    
    return pool, conn


def test_list_trades(mock_db_pool):
    """Test listing trade executions."""
    pool, conn = mock_db_pool
    
    conn.fetch.return_value = [
        {
            "id": 1,
            "trade_id": "TRADE-001",
            "order_id": "ORDER-001",
            "exchange": "bitfinex",
            "symbol": "BTCUSD",
            "side": "BUY",
            "quantity": Decimal("0.5"),
            "price": Decimal("50000"),
            "fee": Decimal("25"),
            "fee_currency": "USD",
            "quote_qty": Decimal("25000"),
            "trade_type": "market",
            "execution_time": datetime(2024, 1, 1, 12, 0, 0),
            "is_paper": True,
        }
    ]
    
    with patch("api.routes.trade_history._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/trades/?limit=10")
    
    assert response.status_code == 200
    payload = response.json()
    assert "trades" in payload
    assert len(payload["trades"]) == 1
    assert payload["trades"][0]["trade_id"] == "TRADE-001"
    assert payload["trades"][0]["symbol"] == "BTCUSD"


def test_list_trades_with_filters(mock_db_pool):
    """Test listing trades with symbol filter."""
    pool, conn = mock_db_pool
    
    conn.fetch.return_value = [
        {
            "id": 1,
            "trade_id": "TRADE-001",
            "order_id": "ORDER-001",
            "exchange": "bitfinex",
            "symbol": "BTCUSD",
            "side": "BUY",
            "quantity": Decimal("0.5"),
            "price": Decimal("50000"),
            "fee": Decimal("25"),
            "fee_currency": "USD",
            "quote_qty": Decimal("25000"),
            "trade_type": "market",
            "execution_time": datetime(2024, 1, 1, 12, 0, 0),
            "is_paper": True,
        }
    ]
    
    with patch("api.routes.trade_history._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/trades/?symbol=BTCUSD&is_paper=true")
    
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["trades"]) == 1


def test_get_trade_by_id(mock_db_pool):
    """Test getting a specific trade."""
    pool, conn = mock_db_pool
    
    conn.fetchrow.return_value = {
        "id": 1,
        "trade_id": "TRADE-001",
        "order_id": "ORDER-001",
        "exchange": "bitfinex",
        "symbol": "BTCUSD",
        "side": "BUY",
        "quantity": Decimal("0.5"),
        "price": Decimal("50000"),
        "fee": Decimal("25"),
        "fee_currency": "USD",
        "quote_qty": Decimal("25000"),
        "trade_type": "market",
        "execution_time": datetime(2024, 1, 1, 12, 0, 0),
        "is_paper": True,
    }
    
    with patch("api.routes.trade_history._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/trades/TRADE-001")
    
    assert response.status_code == 200
    payload = response.json()
    assert payload["trade"]["trade_id"] == "TRADE-001"


def test_get_trade_not_found(mock_db_pool):
    """Test getting a non-existent trade."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = None
    
    with patch("api.routes.trade_history._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/trades/NONEXISTENT")
    
    assert response.status_code == 404


def test_get_order_audit_log(mock_db_pool):
    """Test getting order audit log."""
    pool, conn = mock_db_pool
    
    conn.fetch.return_value = [
        {
            "id": 1,
            "order_id": "ORDER-001",
            "exchange": "bitfinex",
            "symbol": "BTCUSD",
            "side": "BUY",
            "order_type": "market",
            "status": "FILLED",
            "event_type": "FILLED",
            "event_time": datetime(2024, 1, 1, 12, 0, 0),
            "quantity": Decimal("0.5"),
            "filled_quantity": Decimal("0.5"),
            "limit_price": None,
            "stop_price": None,
            "avg_fill_price": Decimal("50000"),
            "metadata": None,
        }
    ]
    
    with patch("api.routes.trade_history._get_db_pool", return_value=asyncio.coroutine(lambda: pool)()):
        client = TestClient(app)
        response = client.get("/trades/audit?order_id=ORDER-001")
    
    assert response.status_code == 200
    payload = response.json()
    assert "audit_log" in payload
    assert len(payload["audit_log"]) == 1
    assert payload["audit_log"][0]["order_id"] == "ORDER-001"
    assert payload["audit_log"][0]["event_type"] == "FILLED"
