"""CoinGecko API client for fetching market cap rankings.

This module provides a simple client to fetch top coins by market cap from
CoinGecko's free API. No API key required.

Rate limits (CoinGecko free tier):
- 10-30 calls/minute
- Cache responses aggressively (5-15 min recommended)
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# CoinGecko free API endpoint
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    """Simple client for CoinGecko API (free tier, no API key)."""

    def __init__(self, timeout: int = 10):
        """Initialize CoinGecko client.

        Args:
            timeout: Request timeout in seconds (default: 10)
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def close(self):
        """Close the HTTP session."""
        if self.session:
            self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.close()
        return False

    def fetch_top_coins_by_market_cap(
        self,
        limit: int = 100,
        vs_currency: str = "usd",
    ) -> list[dict[str, Any]]:
        """Fetch top coins by market cap from CoinGecko.

        Args:
            limit: Number of coins to fetch (max 250 on free tier)
            vs_currency: Quote currency (default: 'usd')

        Returns:
            List of coin data dictionaries with keys:
            - id: CoinGecko coin ID (e.g., 'bitcoin')
            - symbol: Ticker symbol (e.g., 'btc')
            - name: Coin name (e.g., 'Bitcoin')
            - market_cap_rank: Market cap rank (1-based)
            - market_cap: Current market cap in USD
            - current_price: Current price in USD

        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{COINGECKO_API_BASE}/coins/markets"
        params = {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": min(limit, 250),  # CoinGecko free tier max
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "",
        }

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                logger.error(f"Unexpected CoinGecko response format: {type(data)}")
                return []

            logger.info(f"Fetched {len(data)} coins from CoinGecko")
            return data

        except requests.RequestException as e:
            logger.error(f"CoinGecko API request failed: {e}")
            raise

    def get_market_cap_map(self, limit: int = 100) -> dict[str, int]:
        """Get a map of symbol -> market cap rank.

        Args:
            limit: Number of coins to fetch

        Returns:
            Dictionary mapping uppercase symbol to market cap rank (1-based)
            Example: {'BTC': 1, 'ETH': 2, 'XRP': 3, ...}

        Raises:
            requests.RequestException: If API request fails
        """
        coins = self.fetch_top_coins_by_market_cap(limit=limit)
        result = {}

        for coin in coins:
            symbol = str(coin.get("symbol", "")).upper()
            rank = coin.get("market_cap_rank")

            if symbol and rank is not None:
                result[symbol] = int(rank)

        logger.info(f"Built market cap map with {len(result)} symbols")
        return result
