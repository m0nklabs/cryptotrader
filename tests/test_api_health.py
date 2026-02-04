"""Tests for the /system/health API endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app)


def test_health_endpoint_all_ok(client):
    """Test /system/health endpoint when all components are healthy."""
    # Mock HealthChecker.check_all to return all OK statuses
    with patch("core.health.checker.HealthChecker.check_all") as mock_check_all:
        from core.health.checker import HealthStatus

        # Mock check_all to return healthy statuses
        mock_check_all.return_value = {
            "database": HealthStatus(
                status="ok", message="Connected", latency_ms=5.2
            ),
            "ingestion": HealthStatus(
                status="ok",
                message="Active",
                details={"last_run": "2024-01-01T00:00:00Z", "runs_24h": 24},
            ),
        }

        response = client.get("/system/health")

        assert response.status_code == 200
        data = response.json()

        # Check overall status
        assert "overall" in data
        assert data["overall"]["status"] == "ok"

        # Check API status
        assert "api" in data
        assert data["api"]["status"] == "ok"
        assert "uptime_seconds" in data["api"]
        assert data["api"]["uptime_seconds"] >= 0

        # Check database status
        assert "database" in data
        assert data["database"]["status"] == "ok"
        assert data["database"]["message"] == "Connected"
        assert data["database"]["latency_ms"] == 5.2

        # Check ingestion status
        assert "ingestion" in data
        assert data["ingestion"]["status"] == "ok"
        assert "details" in data["ingestion"]


def test_health_endpoint_database_degraded(client):
    """Test /system/health endpoint when database is degraded."""
    with patch("core.health.checker.HealthChecker.check_all") as mock_check_all:
        from core.health.checker import HealthStatus

        mock_check_all.return_value = {
            "database": HealthStatus(
                status="degraded", message="Slow response", latency_ms=150.0
            ),
            "ingestion": HealthStatus(status="ok", message="Active"),
        }

        response = client.get("/system/health")

        assert response.status_code == 200
        data = response.json()

        # Overall status should be degraded
        assert data["overall"]["status"] == "degraded"
        assert data["database"]["status"] == "degraded"
        assert data["database"]["latency_ms"] == 150.0


def test_health_endpoint_component_error(client):
    """Test /system/health endpoint when a component has an error."""
    with patch("core.health.checker.HealthChecker.check_all") as mock_check_all:
        from core.health.checker import HealthStatus

        mock_check_all.return_value = {
            "database": HealthStatus(
                status="error", message="Connection failed", latency_ms=None
            ),
            "ingestion": HealthStatus(status="ok", message="Active"),
        }

        response = client.get("/system/health")

        assert response.status_code == 200
        data = response.json()

        # Overall status should be error
        assert data["overall"]["status"] == "error"
        assert data["database"]["status"] == "error"
        assert data["database"]["message"] == "Connection failed"


def test_health_endpoint_response_shape(client):
    """Test that /system/health response has the expected shape."""
    with patch("core.health.checker.HealthChecker.check_all") as mock_check_all:
        from core.health.checker import HealthStatus

        mock_check_all.return_value = {
            "database": HealthStatus(status="ok", message="OK"),
        }

        response = client.get("/system/health")

        assert response.status_code == 200
        data = response.json()

        # Check required top-level keys
        assert "overall" in data
        assert "api" in data
        assert "database" in data

        # Check overall structure
        assert "status" in data["overall"]
        assert data["overall"]["status"] in ["ok", "degraded", "error"]

        # Check API structure
        assert "status" in data["api"]
        assert "uptime_seconds" in data["api"]
        assert "message" in data["api"]


def test_health_endpoint_uptime_increases(client):
    """Test that API uptime is calculated and is monotonic."""
    response1 = client.get("/system/health")
    data1 = response1.json()
    
    # First call should have uptime >= 0
    assert data1["api"]["uptime_seconds"] >= 0
    
    # Make another call - uptime should be >= the first call (monotonic)
    response2 = client.get("/system/health")
    data2 = response2.json()
    
    # Uptime should be monotonically increasing (or at least not decrease)
    assert data2["api"]["uptime_seconds"] >= data1["api"]["uptime_seconds"]
