"""
Unit tests for BitfinexClient authenticated requests.

Tests the client's use of authentication helper with mocked HTTP requests.
"""

from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient


class TestBitfinexClientAuth:
    """Test BitfinexClient authenticated endpoint integration."""

    @patch.dict("os.environ", {}, clear=True)
    def test_get_wallets_requires_api_credentials(self) -> None:
        """get_wallets should raise ValueError if API credentials not provided."""
        client = BitfinexClient()

        with pytest.raises(ValueError, match="API key and secret required"):
            client.get_wallets()

    @patch("cex.bitfinex.api.bitfinex_client_v2.requests.post")
    def test_get_wallets_calls_auth_endpoint(self, mock_post: Mock) -> None:
        """get_wallets should call the correct authenticated endpoint."""
        # Setup
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_post.return_value = mock_response

        client = BitfinexClient(api_key="test_key", api_secret="test_secret")

        # Execute
        client.get_wallets()

        # Verify
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Check URL (BASE_URL already includes /v2, path is /auth/r/wallets)
        assert "https://api-pub.bitfinex.com/v2/auth/r/wallets" in call_args[0][0]

        # Check headers were provided
        assert "headers" in call_args[1]
        headers = call_args[1]["headers"]
        assert "bfx-nonce" in headers
        assert "bfx-apikey" in headers
        assert "bfx-signature" in headers

    @patch("cex.bitfinex.api.bitfinex_client_v2.requests.post")
    def test_get_wallets_parses_response(self, mock_post: Mock) -> None:
        """get_wallets should parse Bitfinex wallet response correctly."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = [
            ["exchange", "BTC", 1.5, 0.0, 1.5],
            ["exchange", "USD", 10000.0, 0.0, 10000.0],
            ["margin", "ETH", 5.0, 0.1, 4.9],
        ]
        mock_post.return_value = mock_response

        client = BitfinexClient(api_key="test_key", api_secret="test_secret")

        # Execute
        wallets = client.get_wallets()

        # Verify
        assert len(wallets) == 3

        # Check first wallet
        assert wallets[0]["type"] == "exchange"
        assert wallets[0]["currency"] == "BTC"
        assert wallets[0]["balance"] == 1.5
        assert wallets[0]["unsettled_interest"] == 0.0
        assert wallets[0]["available_balance"] == 1.5

        # Check second wallet
        assert wallets[1]["type"] == "exchange"
        assert wallets[1]["currency"] == "USD"
        assert wallets[1]["balance"] == 10000.0

        # Check third wallet
        assert wallets[2]["type"] == "margin"
        assert wallets[2]["currency"] == "ETH"
        assert wallets[2]["balance"] == 5.0
        assert wallets[2]["unsettled_interest"] == 0.1
        assert wallets[2]["available_balance"] == 4.9

    @patch("cex.bitfinex.api.bitfinex_client_v2.requests.post")
    def test_get_wallets_handles_empty_response(self, mock_post: Mock) -> None:
        """get_wallets should handle empty wallet list."""
        # Setup
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_post.return_value = mock_response

        client = BitfinexClient(api_key="test_key", api_secret="test_secret")

        # Execute
        wallets = client.get_wallets()

        # Verify
        assert wallets == []

    @patch("cex.bitfinex.api.bitfinex_client_v2.requests.post")
    def test_get_wallets_uses_build_auth_headers(self, mock_post: Mock) -> None:
        """get_wallets should use build_auth_headers to generate auth headers."""
        # Setup
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_post.return_value = mock_response

        client = BitfinexClient(api_key="my_key_123", api_secret="my_secret_456")

        # Execute
        client.get_wallets()

        # Verify headers contain required auth fields
        headers = mock_post.call_args[1]["headers"]
        assert headers["bfx-apikey"] == "my_key_123"
        assert "bfx-nonce" in headers
        assert "bfx-signature" in headers
        assert len(headers["bfx-signature"]) == 96  # SHA384 hex length

    @patch("cex.bitfinex.api.bitfinex_client_v2.requests.post")
    def test_get_wallets_handles_null_available_balance(self, mock_post: Mock) -> None:
        """get_wallets should handle None/null available_balance gracefully."""
        # Setup - some wallets may have null available_balance
        mock_response = Mock()
        mock_response.json.return_value = [
            ["exchange", "BTC", 1.5, 0.0, None],  # null available_balance
        ]
        mock_post.return_value = mock_response

        client = BitfinexClient(api_key="test_key", api_secret="test_secret")

        # Execute
        wallets = client.get_wallets()

        # Verify
        assert len(wallets) == 1
        assert wallets[0]["available_balance"] is None
