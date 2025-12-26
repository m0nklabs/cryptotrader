"""Tests for the system status API endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app)


def test_system_status_endpoint_success(client):
    """Test system status endpoint with successful database connection."""
    # Mock the stores and database
    with patch("api.main._get_stores") as mock_get_stores:
        mock_stores = Mock()
        mock_get_stores.return_value = mock_stores

        # Mock engine and connection
        mock_engine = Mock()
        mock_conn = MagicMock()
        mock_stores._get_engine.return_value = mock_engine
        mock_engine.begin.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = Mock(return_value=False)

        # Mock SQLAlchemy text function
        def text_func(sql):
            return Mock(text=sql)

        mock_stores._require_sqlalchemy.return_value = (Mock(), text_func)

        # Mock the query result
        mock_result = Mock()
        mock_result.scalar.return_value = 1
        mock_conn.execute.return_value = mock_result

        # Call the endpoint via HTTP
        response = client.get("/system/status")

        # Verify HTTP response
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "backend" in data
        assert "database" in data
        assert "timestamp" in data

        # Verify backend status
        assert data["backend"]["status"] == "ok"
        assert "uptime_seconds" in data["backend"]
        assert isinstance(data["backend"]["uptime_seconds"], int)

        # Verify database status
        assert data["database"]["status"] == "ok"
        assert data["database"]["connected"] is True
        assert "latency_ms" in data["database"]
        assert data["database"]["latency_ms"] is not None


def test_system_status_endpoint_database_error(client):
    """Test system status endpoint when database connection fails."""
    # Mock the stores to raise an error
    with patch("api.main._get_stores") as mock_get_stores:
        mock_get_stores.side_effect = RuntimeError("DATABASE_URL environment variable is required")

        # Call the endpoint via HTTP
        response = client.get("/system/status")

        # Verify HTTP response
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "backend" in data
        assert "database" in data
        assert "timestamp" in data

        # Backend should still be ok
        assert data["backend"]["status"] == "ok"

        # Database should show error
        assert data["database"]["status"] == "error"
        assert data["database"]["connected"] is False
        assert data["database"]["latency_ms"] is None
        assert "error" in data["database"]


def test_system_status_endpoint_exists():
    """Test that the system status endpoint is registered."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/system/status" in routes
