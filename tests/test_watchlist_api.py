"""Tests for watchlist API endpoints."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool."""
    pool = MagicMock()  # Sync mock — pool.acquire() is a sync call in asyncpg
    conn = AsyncMock()  # Async mock — conn.fetch(), conn.fetchrow() are async

    # pool.acquire() returns async context manager (sync call, async CM)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    return pool, conn


def test_list_watchlists(mock_db_pool):
    """Test listing all watchlists."""
    pool, conn = mock_db_pool

    conn.fetch.return_value = [
        {
            "id": 1,
            "name": "My Favorites",
            "description": "Top picks",
            "is_default": True,
            "sort_order": 0,
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "updated_at": datetime(2024, 1, 1, 12, 0, 0),
        }
    ]

    with patch("api.routes.watchlist._get_db_pool", new_callable=AsyncMock, return_value=pool):
        client = TestClient(app)
        response = client.get("/watchlist/")

    assert response.status_code == 200
    payload = response.json()
    assert "watchlists" in payload
    assert len(payload["watchlists"]) == 1
    assert payload["watchlists"][0]["name"] == "My Favorites"


def test_get_watchlist_with_items(mock_db_pool):
    """Test getting a specific watchlist with items."""
    pool, conn = mock_db_pool

    conn.fetchrow.return_value = {
        "id": 1,
        "name": "My Favorites",
        "description": "Top picks",
        "is_default": True,
        "created_at": datetime(2024, 1, 1, 12, 0, 0),
        "updated_at": datetime(2024, 1, 1, 12, 0, 0),
    }

    conn.fetch.side_effect = [
        [  # watchlist items
            {
                "id": 1,
                "exchange": "bitfinex",
                "symbol": "BTCUSD",
                "sort_order": 0,
                "notes": "Bitcoin",
            }
        ],
        [],  # column preferences
    ]

    with patch("api.routes.watchlist._get_db_pool", new_callable=AsyncMock, return_value=pool):
        client = TestClient(app)
        response = client.get("/watchlist/1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["watchlist"]["id"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["symbol"] == "BTCUSD"


def test_get_watchlist_not_found(mock_db_pool):
    """Test getting a non-existent watchlist."""
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = None

    with patch("api.routes.watchlist._get_db_pool", new_callable=AsyncMock, return_value=pool):
        client = TestClient(app)
        response = client.get("/watchlist/999")

    assert response.status_code == 404


def test_create_watchlist(mock_db_pool):
    """Test creating a new watchlist."""
    pool, conn = mock_db_pool
    conn.fetchval.return_value = 1

    with patch("api.routes.watchlist._get_db_pool", new_callable=AsyncMock, return_value=pool):
        client = TestClient(app)
        response = client.post("/watchlist/", json={"name": "New Watchlist", "description": "Test list"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["watchlist_id"] == 1


def test_delete_watchlist(mock_db_pool):
    """Test deleting a watchlist."""
    pool, conn = mock_db_pool
    conn.execute.return_value = "DELETE 1"

    with patch("api.routes.watchlist._get_db_pool", new_callable=AsyncMock, return_value=pool):
        client = TestClient(app)
        response = client.delete("/watchlist/1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
