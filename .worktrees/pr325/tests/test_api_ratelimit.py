"""Tests for the /ratelimit API endpoints."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from core.ratelimit import get_tracker


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_tracker():
    """Clear the rate limit tracker before each test."""
    tracker = get_tracker()
    tracker._limits.clear()
    yield
    tracker._limits.clear()


def test_get_rate_limit_status_empty(client):
    """Test /ratelimit/status with no tracked limits."""
    response = client.get("/ratelimit/status")
    assert response.status_code == 200
    data = response.json()
    assert "limits" in data
    assert "count" in data
    assert data["limits"] == []
    assert data["count"] == 0


def test_get_rate_limit_status_with_data(client):
    """Test /ratelimit/status with tracked limits."""
    tracker = get_tracker()

    # Add some rate limit data
    tracker.update(
        exchange="binance",
        endpoint="/api/v3/ticker",
        limit=1200,
        remaining=800,
        reset_at=time.time() + 60,
    )
    tracker.update(
        exchange="kraken",
        endpoint="/0/public/Ticker",
        limit=15,
        remaining=10,
        reset_at=time.time() + 30,
    )

    response = client.get("/ratelimit/status")
    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 2
    assert len(data["limits"]) == 2

    # Check response structure
    limit = data["limits"][0]
    assert "exchange" in limit
    assert "endpoint" in limit
    assert "limit" in limit
    assert "used" in limit
    assert "remaining" in limit
    assert "usage_percent" in limit
    assert "reset_at" in limit
    assert "reset_in_seconds" in limit
    assert "status" in limit
    assert "window_seconds" in limit

    # Check one specific limit
    binance_limit = next(limit for limit in data["limits"] if limit["exchange"] == "binance")
    assert binance_limit["limit"] == 1200
    assert binance_limit["remaining"] == 800
    assert binance_limit["used"] == 400
    assert binance_limit["usage_percent"] == pytest.approx(33.33, rel=0.01)
    assert binance_limit["status"] == "ok"


def test_get_rate_limit_status_filter_by_exchange(client):
    """Test /ratelimit/status with exchange filter."""
    tracker = get_tracker()

    # Add data for multiple exchanges
    tracker.update("binance", "/api/v3/ticker", 1200, 800, time.time() + 60)
    tracker.update("kraken", "/0/public/Ticker", 15, 10, time.time() + 30)
    tracker.update("binance", "/api/v3/depth", 100, 50, time.time() + 45)

    # Filter by binance
    response = client.get("/ratelimit/status?exchange=binance")
    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 2
    assert all(limit["exchange"] == "binance" for limit in data["limits"])


def test_get_rate_limit_status_usage_percent_and_status(client):
    """Test that usage_percent and status are calculated correctly."""
    tracker = get_tracker()

    # Add limits with different usage levels
    tracker.update("exchange1", "/endpoint1", 100, 80, time.time() + 60)  # 20% used - ok
    tracker.update("exchange2", "/endpoint2", 100, 25, time.time() + 60)  # 75% used - warning
    tracker.update("exchange3", "/endpoint3", 100, 5, time.time() + 60)  # 95% used - critical

    response = client.get("/ratelimit/status")
    assert response.status_code == 200
    data = response.json()

    limits_by_exchange = {limit["exchange"]: limit for limit in data["limits"]}

    assert limits_by_exchange["exchange1"]["usage_percent"] == 20.0
    assert limits_by_exchange["exchange1"]["status"] == "ok"

    assert limits_by_exchange["exchange2"]["usage_percent"] == 75.0
    assert limits_by_exchange["exchange2"]["status"] == "warning"

    assert limits_by_exchange["exchange3"]["usage_percent"] == 95.0
    assert limits_by_exchange["exchange3"]["status"] == "critical"


def test_get_exchanges_empty(client):
    """Test /ratelimit/exchanges with no tracked exchanges."""
    response = client.get("/ratelimit/exchanges")
    assert response.status_code == 200
    data = response.json()
    assert "exchanges" in data
    assert "count" in data
    assert data["exchanges"] == []
    assert data["count"] == 0


def test_get_exchanges_with_data(client):
    """Test /ratelimit/exchanges with tracked exchanges."""
    tracker = get_tracker()

    # Add data for multiple exchanges with multiple endpoints
    tracker.update("binance", "/api/v3/ticker", 1200, 800, time.time() + 60)
    tracker.update("binance", "/api/v3/depth", 100, 50, time.time() + 45)
    tracker.update("kraken", "/0/public/Ticker", 15, 10, time.time() + 30)
    tracker.update("coinbase", "/products", 10, 5, time.time() + 20)

    response = client.get("/ratelimit/exchanges")
    assert response.status_code == 200
    data = response.json()

    # Should have unique, sorted exchanges
    assert data["count"] == 3
    assert data["exchanges"] == ["binance", "coinbase", "kraken"]


def test_rate_limit_status_clears_expired(client):
    """Test that expired rate limits are removed."""
    tracker = get_tracker()

    # Add an expired limit
    tracker.update("exchange1", "/endpoint1", 100, 50, time.time() - 10)  # Expired
    tracker.update("exchange2", "/endpoint2", 100, 50, time.time() + 60)  # Active

    response = client.get("/ratelimit/status")
    assert response.status_code == 200
    data = response.json()

    # Should only return the active limit
    assert data["count"] == 1
    assert data["limits"][0]["exchange"] == "exchange2"


def test_rate_limit_status_ordering(client):
    """Test that rate limits are returned in a consistent order."""
    tracker = get_tracker()

    # Add limits in a specific order
    tracker.update("zebra", "/endpoint", 100, 50, time.time() + 60)
    tracker.update("apple", "/endpoint", 100, 50, time.time() + 60)
    tracker.update("monkey", "/endpoint", 100, 50, time.time() + 60)

    response = client.get("/ratelimit/status")
    assert response.status_code == 200
    data = response.json()

    # The tracker maintains insertion order via dict
    exchanges = [limit["exchange"] for limit in data["limits"]]
    assert len(exchanges) == 3
    # Verify all exchanges are present
    assert set(exchanges) == {"zebra", "apple", "monkey"}
