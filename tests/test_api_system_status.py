"""Tests for the system status API endpoint."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.asyncio
async def test_system_status_endpoint_success():
    """Test system status endpoint with successful database connection."""
    from api.main import get_system_status

    # Mock the stores and database
    with patch("api.main._get_stores") as mock_get_stores:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_text = MagicMock()

        # Mock the engine and connection
        mock_stores = MagicMock()
        mock_stores._get_engine.return_value = mock_engine
        mock_stores._require_sqlalchemy.return_value = (None, mock_text)
        mock_get_stores.return_value = mock_stores

        # Mock begin context manager
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_engine.begin.return_value.__exit__.return_value = None

        # Mock the query result
        mock_conn.execute.return_value.scalar.return_value = 1

        # Call the endpoint
        response = await get_system_status()

        # Verify response structure
        assert "backend" in response
        assert "database" in response
        assert "timestamp" in response

        # Verify backend status
        assert response["backend"]["status"] == "ok"
        assert "uptime_seconds" in response["backend"]
        assert isinstance(response["backend"]["uptime_seconds"], int)

        # Verify database status
        assert response["database"]["status"] == "ok"
        assert response["database"]["connected"] is True
        assert "latency_ms" in response["database"]
        assert response["database"]["latency_ms"] is not None


@pytest.mark.asyncio
async def test_system_status_endpoint_database_error():
    """Test system status endpoint when database connection fails."""
    from api.main import get_system_status

    # Mock the stores to raise an error
    with patch("api.main._get_stores") as mock_get_stores:
        mock_get_stores.side_effect = RuntimeError("DATABASE_URL environment variable is required")

        # Call the endpoint (should not raise, but return error status)
        response = await get_system_status()

        # Verify response structure
        assert "backend" in response
        assert "database" in response
        assert "timestamp" in response

        # Backend should still be ok
        assert response["backend"]["status"] == "ok"

        # Database should show error
        assert response["database"]["status"] == "error"
        assert response["database"]["connected"] is False
        assert response["database"]["latency_ms"] is None
        assert "error" in response["database"]


def test_system_status_endpoint_exists():
    """Test that the system status endpoint is registered."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/api/system/status" in routes
