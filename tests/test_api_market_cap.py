"""Tests for market cap API endpoint."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_market_cap_endpoint_exists():
    """Test that the /market-cap endpoint is registered."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/market-cap" in routes


@patch("api.main._refresh_market_cap_cache")
def test_market_cap_endpoint_response(mock_refresh):
    """Test market cap endpoint returns expected format."""
    from fastapi.testclient import TestClient
    from api.main import app

    # Mock the refresh function to return test data
    mock_refresh.return_value = {"BTC": 1, "ETH": 2, "XRP": 3}

    client = TestClient(app)
    response = client.get("/market-cap")

    assert response.status_code == 200
    data = response.json()

    assert "rankings" in data
    assert "cached" in data
    assert "source" in data
    assert "last_updated" in data

    assert data["rankings"] == {"BTC": 1, "ETH": 2, "XRP": 3}


@patch("api.main._get_coingecko_client")
def test_market_cap_cache_refresh(mock_get_client):
    """Test that market cap cache refresh works correctly."""
    from api.main import _refresh_market_cap_cache

    # Mock CoinGecko client
    mock_client = mock_get_client.return_value
    mock_client.get_market_cap_map.return_value = {
        "BTC": 1,
        "ETH": 2,
        "SOL": 4,
    }

    result = _refresh_market_cap_cache()

    assert result == {"BTC": 1, "ETH": 2, "SOL": 4}
    mock_client.get_market_cap_map.assert_called_once()


@patch("api.main._get_coingecko_client")
def test_market_cap_fallback_on_error(mock_get_client):
    """Test that fallback rankings are used when API fails."""
    from api.main import _refresh_market_cap_cache, FALLBACK_MARKET_CAP_RANK
    import api.main

    # Clear the cache to ensure clean test
    api.main._market_cap_cache = {}
    api.main._market_cap_cache_time = 0

    # Mock CoinGecko client to raise an error
    mock_client = mock_get_client.return_value
    mock_client.get_market_cap_map.side_effect = Exception("API Error")

    result = _refresh_market_cap_cache()

    # Should return fallback rankings
    assert result == FALLBACK_MARKET_CAP_RANK
