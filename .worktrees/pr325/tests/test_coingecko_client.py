"""Tests for CoinGecko market cap client."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_cap.coingecko import CoinGeckoClient


def test_coingecko_client_init():
    """Test CoinGecko client initialization."""
    client = CoinGeckoClient(timeout=5)
    assert client.timeout == 5
    assert client.session is not None
    assert "Accept" in client.session.headers


@patch("core.market_cap.coingecko.requests.Session")
def test_fetch_top_coins_success(mock_session_class):
    """Test fetching top coins successfully."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "market_cap_rank": 1,
            "market_cap": 1000000000000,
            "current_price": 50000,
        },
        {
            "id": "ethereum",
            "symbol": "eth",
            "name": "Ethereum",
            "market_cap_rank": 2,
            "market_cap": 500000000000,
            "current_price": 3000,
        },
    ]

    # Mock session
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_session_class.return_value = mock_session

    client = CoinGeckoClient()
    coins = client.fetch_top_coins_by_market_cap(limit=10)

    assert len(coins) == 2
    assert coins[0]["symbol"] == "btc"
    assert coins[0]["market_cap_rank"] == 1
    assert coins[1]["symbol"] == "eth"
    assert coins[1]["market_cap_rank"] == 2


@patch("core.market_cap.coingecko.requests.Session")
def test_get_market_cap_map_success(mock_session_class):
    """Test getting market cap map."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "market_cap_rank": 1,
        },
        {
            "id": "ethereum",
            "symbol": "eth",
            "name": "Ethereum",
            "market_cap_rank": 2,
        },
        {
            "id": "ripple",
            "symbol": "xrp",
            "name": "XRP",
            "market_cap_rank": 3,
        },
    ]

    # Mock session
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_session_class.return_value = mock_session

    client = CoinGeckoClient()
    market_cap_map = client.get_market_cap_map(limit=10)

    assert market_cap_map == {"BTC": 1, "ETH": 2, "XRP": 3}


@patch("core.market_cap.coingecko.requests.Session")
def test_fetch_handles_api_error(mock_session_class):
    """Test that API errors are raised properly."""
    # Mock error response
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("API Error")

    # Mock session
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_session_class.return_value = mock_session

    client = CoinGeckoClient()

    with pytest.raises(Exception):
        client.fetch_top_coins_by_market_cap()


@patch("core.market_cap.coingecko.requests.Session")
def test_fetch_handles_invalid_response(mock_session_class):
    """Test handling of invalid response format."""
    # Mock invalid response (not a list)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"error": "something went wrong"}

    # Mock session
    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_session_class.return_value = mock_session

    client = CoinGeckoClient()
    coins = client.fetch_top_coins_by_market_cap()

    # Should return empty list for invalid format
    assert coins == []
