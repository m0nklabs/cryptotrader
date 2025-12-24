"""CoinGecko API client for fetching market cap rankings.

Uses the free tier API (no API key required).
Rate limit: 10-30 calls/minute on free tier.
"""

from __future__ import annotations

import time
from typing import Any

import requests


class CoinGeckoClient:
    """Client for CoinGecko API (free tier, no API key)."""

    BASE_URL = "https://api.coingecko.com/api/v3"
    DEFAULT_TIMEOUT = 10  # seconds
    
    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "cryptotrader/2.0",
        })
    
    def get_top_coins_by_market_cap(
        self,
        *,
        limit: int = 100,
        vs_currency: str = "usd",
    ) -> list[dict[str, Any]]:
        """Fetch top N coins by market cap.
        
        Args:
            limit: Number of coins to fetch (max 250 per page on free tier)
            vs_currency: Currency for market cap values (default: usd)
        
        Returns:
            List of coin data dictionaries with fields:
            - id: CoinGecko coin ID (e.g., "bitcoin")
            - symbol: Coin symbol (e.g., "btc")
            - name: Coin name (e.g., "Bitcoin")
            - market_cap_rank: Ranking by market cap (1, 2, 3, ...)
            - market_cap: Market cap in vs_currency
        
        Raises:
            RuntimeError: If API request fails
        """
        url = f"{self.BASE_URL}/coins/markets"
        params = {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": min(limit, 250),  # API max per page
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "",
            "locale": "en",
        }
        
        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected response format: {type(data)}")
            
            # Extract relevant fields
            results = []
            for coin in data:
                if not isinstance(coin, dict):
                    continue
                
                # Only include coins with valid market cap rank
                rank = coin.get("market_cap_rank")
                if rank is None or not isinstance(rank, (int, float)):
                    continue
                
                results.append({
                    "id": str(coin.get("id", "")),
                    "symbol": str(coin.get("symbol", "")).upper(),
                    "name": str(coin.get("name", "")),
                    "market_cap_rank": int(rank),
                    "market_cap": float(coin.get("market_cap") or 0),
                })
            
            return results
        
        except requests.RequestException as exc:
            raise RuntimeError(f"CoinGecko API request failed: {exc}") from exc
    
    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()


def fetch_and_format_market_caps(*, limit: int = 100) -> list[dict[str, Any]]:
    """Convenience function to fetch market cap data.
    
    Args:
        limit: Number of top coins to fetch
    
    Returns:
        List of formatted market cap records ready for database insertion
    """
    client = CoinGeckoClient()
    try:
        coins = client.get_top_coins_by_market_cap(limit=limit)
        return coins
    finally:
        client.close()
