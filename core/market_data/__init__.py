"""Market data ingestion.

Authoritative specs live in `docs/` (see `docs/ARCHITECTURE.md` and `docs/TODO.md`).
"""

from core.market_data.base import ExchangeProvider, TimeframeSpec
from core.market_data.binance_provider import BinanceProvider
from core.market_data.bitfinex_provider import BitfinexProvider
from core.market_data.kraken_provider import KrakenProvider

__all__ = [
    "ExchangeProvider",
    "TimeframeSpec",
    "BinanceProvider",
    "BitfinexProvider",
    "KrakenProvider",
]


def get_provider(exchange: str) -> ExchangeProvider:
    """Factory function to get the appropriate exchange provider."""
    providers = {
        "binance": BinanceProvider(),
        "bitfinex": BitfinexProvider(),
        "kraken": KrakenProvider(),
    }
    
    exchange_lower = exchange.lower().strip()
    if exchange_lower not in providers:
        raise ValueError(f"Unsupported exchange: {exchange}. Supported: {', '.join(providers.keys())}")
    
    return providers[exchange_lower]
