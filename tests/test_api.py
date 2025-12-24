"""Tests for the FastAPI read-only API."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_api_module_imports():
    """Test that the API module can be imported."""
    from api import main

    assert hasattr(main, "app")
    assert hasattr(main, "health")
    assert hasattr(main, "get_latest_candles")


def test_fastapi_app_configuration():
    """Test that the FastAPI app is properly configured."""
    from api.main import app

    assert app.title == "CryptoTrader Read-Only API"
    assert app.description == "Minimal API for candles, health checks, and ingestion status"
    assert app.version == "1.0.0"


def test_health_endpoint_exists():
    """Test that the health endpoint is registered."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/health" in routes


def test_candles_endpoint_exists():
    """Test that the candles/latest endpoint is registered."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/candles/latest" in routes


@pytest.mark.asyncio
async def test_health_endpoint_no_database():
    """Test health endpoint behavior when DATABASE_URL is not set."""
    from fastapi import HTTPException

    from api.main import health

    # Mock the stores to raise an error
    with patch("api.main._get_stores") as mock_get_stores:
        mock_get_stores.side_effect = RuntimeError("DATABASE_URL environment variable is required")

        with pytest.raises(HTTPException) as exc_info:
            await health()

        assert exc_info.value.status_code == 503
        assert "connected" in exc_info.value.detail["database"]
        assert exc_info.value.detail["database"]["connected"] is False


def test_as_utc_helper():
    """Test the _as_utc helper function."""
    from datetime import datetime, timezone

    from api.main import _as_utc

    # Test with naive datetime
    naive_dt = datetime(2025, 1, 1, 12, 0, 0)
    utc_dt = _as_utc(naive_dt)
    assert utc_dt.tzinfo == timezone.utc

    # Test with aware datetime
    aware_dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    utc_dt = _as_utc(aware_dt)
    assert utc_dt.tzinfo == timezone.utc


def test_run_api_script_imports():
    """Test that the run_api script can be imported."""
    from scripts import run_api

    assert hasattr(run_api, "main")
