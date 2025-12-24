from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data import BinanceProvider, BitfinexProvider, KrakenProvider, get_provider
from core.market_data.base import TimeframeSpec


def test_get_provider_returns_binance() -> None:
    provider = get_provider("binance")
    assert isinstance(provider, BinanceProvider)
    assert provider.exchange_name == "binance"


def test_get_provider_returns_bitfinex() -> None:
    provider = get_provider("bitfinex")
    assert isinstance(provider, BitfinexProvider)
    assert provider.exchange_name == "bitfinex"


def test_get_provider_returns_kraken() -> None:
    provider = get_provider("kraken")
    assert isinstance(provider, KrakenProvider)
    assert provider.exchange_name == "kraken"


def test_get_provider_case_insensitive() -> None:
    provider = get_provider("BINANCE")
    assert isinstance(provider, BinanceProvider)


def test_get_provider_raises_on_unknown_exchange() -> None:
    with pytest.raises(ValueError, match="Unsupported exchange"):
        get_provider("unknown_exchange")


def test_bitfinex_provider_timeframe_spec() -> None:
    provider = BitfinexProvider()
    
    spec_1m = provider.get_timeframe_spec("1m")
    assert spec_1m.api == "1m"
    assert spec_1m.delta == timedelta(minutes=1)
    assert spec_1m.step_ms == 60_000
    
    spec_1h = provider.get_timeframe_spec("1h")
    assert spec_1h.api == "1h"
    assert spec_1h.delta == timedelta(hours=1)
    
    spec_1d = provider.get_timeframe_spec("1d")
    assert spec_1d.api == "1D"
    assert spec_1d.delta == timedelta(days=1)


def test_bitfinex_provider_unsupported_timeframe() -> None:
    provider = BitfinexProvider()
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        provider.get_timeframe_spec("2h")


def test_bitfinex_normalize_symbol() -> None:
    provider = BitfinexProvider()
    
    assert provider._normalize_symbol("BTCUSD") == "tBTCUSD"
    assert provider._normalize_symbol(" ETHUSD ") == "tETHUSD"
    assert provider._normalize_symbol("tXRPUSD") == "tXRPUSD"


def test_bitfinex_normalize_symbol_requires_value() -> None:
    provider = BitfinexProvider()
    with pytest.raises(ValueError, match="symbol is required"):
        provider._normalize_symbol("   ")


def test_binance_provider_timeframe_spec() -> None:
    provider = BinanceProvider()
    
    spec_1m = provider.get_timeframe_spec("1m")
    assert spec_1m.api == "1m"
    assert spec_1m.delta == timedelta(minutes=1)
    assert spec_1m.step_ms == 60_000
    
    spec_1h = provider.get_timeframe_spec("1h")
    assert spec_1h.api == "1h"
    assert spec_1h.delta == timedelta(hours=1)
    
    spec_1d = provider.get_timeframe_spec("1d")
    assert spec_1d.api == "1d"
    assert spec_1d.delta == timedelta(days=1)


def test_binance_provider_unsupported_timeframe() -> None:
    provider = BinanceProvider()
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        provider.get_timeframe_spec("2h")


def test_binance_normalize_symbol() -> None:
    provider = BinanceProvider()
    
    # Binance converts USD to USDT
    assert provider._normalize_symbol("BTCUSD") == "BTCUSDT"
    assert provider._normalize_symbol(" ethusd ") == "ETHUSDT"
    
    # Already USDT should stay USDT
    assert provider._normalize_symbol("BTCUSDT") == "BTCUSDT"


def test_binance_normalize_symbol_requires_value() -> None:
    provider = BinanceProvider()
    with pytest.raises(ValueError, match="symbol is required"):
        provider._normalize_symbol("   ")


def test_kraken_provider_timeframe_spec() -> None:
    provider = KrakenProvider()
    
    spec_1m = provider.get_timeframe_spec("1m")
    assert spec_1m.api == "1"
    assert spec_1m.delta == timedelta(minutes=1)
    assert spec_1m.step_ms == 60_000
    
    spec_1h = provider.get_timeframe_spec("1h")
    assert spec_1h.api == "60"
    assert spec_1h.delta == timedelta(hours=1)
    
    spec_4h = provider.get_timeframe_spec("4h")
    assert spec_4h.api == "240"
    assert spec_4h.delta == timedelta(hours=4)


def test_kraken_provider_unsupported_timeframe() -> None:
    provider = KrakenProvider()
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        provider.get_timeframe_spec("2h")


def test_kraken_normalize_symbol() -> None:
    provider = KrakenProvider()
    
    # Known mappings
    assert provider._normalize_symbol("BTCUSD") == "XXBTZUSD"
    assert provider._normalize_symbol("ETHUSD") == "XETHZUSD"
    assert provider._normalize_symbol("BTCEUR") == "XXBTZEUR"
    
    # Unknown symbols pass through
    assert provider._normalize_symbol("SOLUSD") == "SOLUSD"


def test_kraken_normalize_symbol_requires_value() -> None:
    provider = KrakenProvider()
    with pytest.raises(ValueError, match="symbol is required"):
        provider._normalize_symbol("   ")


def test_providers_to_ms() -> None:
    bitfinex = BitfinexProvider()
    binance = BinanceProvider()
    kraken = KrakenProvider()
    
    dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    expected_ms = int(dt.timestamp() * 1000)
    
    assert bitfinex._to_ms(dt) == expected_ms
    assert binance._to_ms(dt) == expected_ms
    assert kraken._to_ms(dt) == expected_ms
