"""
Integration tests for Bitfinex API.

These tests require BITFINEX_API_KEY and BITFINEX_API_SECRET environment variables.
Run with: pytest -m integration
"""

import os

import pytest

# Skip all tests in this module if API keys are not set
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("BITFINEX_API_KEY"),
        reason="BITFINEX_API_KEY not set",
    ),
]


class TestBitfinexAPI:
    """Integration tests for Bitfinex exchange API."""

    @pytest.fixture
    def api_credentials(self):
        """Get API credentials from environment."""
        return {
            "api_key": os.getenv("BITFINEX_API_KEY"),
            "api_secret": os.getenv("BITFINEX_API_SECRET"),
        }

    def test_fetch_ticker(self, api_credentials):
        """Test fetching ticker data from Bitfinex."""
        # TODO: Implement when exchange adapter is ready
        # This is a template for Copilot to expand
        assert api_credentials["api_key"] is not None

    def test_fetch_ohlcv(self, api_credentials):
        """Test fetching OHLCV candles from Bitfinex."""
        # TODO: Implement when exchange adapter is ready
        assert api_credentials["api_key"] is not None

    def test_fetch_orderbook(self, api_credentials):
        """Test fetching orderbook from Bitfinex."""
        # TODO: Implement when exchange adapter is ready
        assert api_credentials["api_key"] is not None
