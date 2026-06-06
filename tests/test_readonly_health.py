"""Tests for the read-only /health endpoint."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app)


def test_health_returns_200(client):
    """Test /health returns HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_healthz_returns_200(client):
    """Test /healthz returns HTTP 200."""
    response = client.get("/healthz")
    assert response.status_code == 200


def test_health_response_shape(client):
    """Test /health returns status, uptime_seconds, and version."""
    response = client.get("/health")
    data = response.json()

    assert "status" in data
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], int)
    assert data["uptime_seconds"] >= 0
    assert "version" in data
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_health_no_database_dependency(client):
    """Test /health works without database being available.

    This verifies the endpoint does not depend on the database stores.
    """
    # Patch _get_stores to raise - if the endpoint still works,
    # it's not calling _get_stores()
    import api.main as main_module

    original_get_stores = main_module._get_stores
    main_module._get_stores = lambda: (_ for _ in ()).throw(
        RuntimeError("DATABASE_URL not set")
    )

    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "database" not in data  # No DB info in response
    finally:
        main_module._get_stores = original_get_stores


def test_health_uptime_increases(client):
    """Test that uptime_seconds is monotonically increasing."""
    response1 = client.get("/health")
    data1 = response1.json()

    time.sleep(0.1)

    response2 = client.get("/health")
    data2 = response2.json()

    assert data2["uptime_seconds"] >= data1["uptime_seconds"]


def test_health_no_http_exception(client):
    """Test /health never raises HTTPException (always 200)."""
    # Even if called many times, should always return 200
    for _ in range(5):
        response = client.get("/health")
        assert response.status_code == 200
