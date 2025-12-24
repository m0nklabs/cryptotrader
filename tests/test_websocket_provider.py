"""
Tests for WebSocket Candle Provider
====================================

Tests the BitfinexWebSocketCandleProvider implementation.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest

from core.market_data.websocket_provider import BitfinexWebSocketCandleProvider
from core.types import Candle


class TestBitfinexWebSocketCandleProvider:
    """Test suite for BitfinexWebSocketCandleProvider."""

    def test_initialization(self):
        """Test provider initialization."""
        provider = BitfinexWebSocketCandleProvider()

        assert provider.exchange == "bitfinex"
        assert provider.ws_client is not None
        assert len(provider.subscriptions) == 0

    def test_initialization_custom_exchange(self):
        """Test provider with custom exchange name."""
        provider = BitfinexWebSocketCandleProvider(exchange="bitfinex-us")
        assert provider.exchange == "bitfinex-us"

    def test_timeframe_mapping(self):
        """Test timeframe conversion to Bitfinex API format."""
        assert BitfinexWebSocketCandleProvider.TIMEFRAME_MAP["1m"] == "1m"
        assert BitfinexWebSocketCandleProvider.TIMEFRAME_MAP["5m"] == "5m"
        assert BitfinexWebSocketCandleProvider.TIMEFRAME_MAP["15m"] == "15m"
        assert BitfinexWebSocketCandleProvider.TIMEFRAME_MAP["1h"] == "1h"
        assert BitfinexWebSocketCandleProvider.TIMEFRAME_MAP["4h"] == "4h"
        assert BitfinexWebSocketCandleProvider.TIMEFRAME_MAP["1d"] == "1D"

    def test_subscribe(self):
        """Test subscribing to candle updates."""
        provider = BitfinexWebSocketCandleProvider()
        provider.ws_client = Mock()
        callback = Mock()

        provider.subscribe("BTCUSD", "1m", callback)

        # Check subscription was added
        assert "tBTCUSD:1m" in provider.subscriptions

        # Check WebSocket client was called
        provider.ws_client.subscribe_candles.assert_called_once()
        call_args = provider.ws_client.subscribe_candles.call_args[0]
        assert call_args[0] == "tBTCUSD"
        assert call_args[1] == "1m"

    def test_subscribe_with_t_prefix(self):
        """Test subscribing with symbol already having 't' prefix."""
        provider = BitfinexWebSocketCandleProvider()
        provider.ws_client = Mock()

        provider.subscribe("tETHUSD", "5m")

        assert "tETHUSD:5m" in provider.subscriptions

    def test_subscribe_unsupported_timeframe(self):
        """Test subscribing with unsupported timeframe raises error."""
        provider = BitfinexWebSocketCandleProvider()

        with pytest.raises(ValueError, match="Unsupported timeframe"):
            provider.subscribe("BTCUSD", "2h")

    def test_parse_candle(self):
        """Test parsing raw candle data to Candle object."""
        provider = BitfinexWebSocketCandleProvider()

        candle_data = {
            "timestamp": 1640000000000,  # 2021-12-20 13:33:20 UTC
            "open": 50000.0,
            "close": 50100.0,
            "high": 50200.0,
            "low": 49900.0,
            "volume": 10.5,
        }

        candle = provider._parse_candle("tBTCUSD", "1m", candle_data)

        assert isinstance(candle, Candle)
        assert candle.symbol == "BTCUSD"
        assert candle.exchange == "bitfinex"
        assert candle.timeframe == "1m"
        assert candle.open == Decimal("50000.0")
        assert candle.close == Decimal("50100.0")
        assert candle.high == Decimal("50200.0")
        assert candle.low == Decimal("49900.0")
        assert candle.volume == Decimal("10.5")

        # Check timestamps
        assert candle.open_time == datetime.fromtimestamp(1640000000, tz=timezone.utc)
        assert candle.close_time == datetime.fromtimestamp(1640000060, tz=timezone.utc)

    def test_parse_candle_different_timeframes(self):
        """Test parsing candles with different timeframes."""
        provider = BitfinexWebSocketCandleProvider()

        candle_data = {
            "timestamp": 1640000000000,
            "open": 50000.0,
            "close": 50100.0,
            "high": 50200.0,
            "low": 49900.0,
            "volume": 10.5,
        }

        # 5m candle
        candle_5m = provider._parse_candle("tBTCUSD", "5m", candle_data)
        time_diff_5m = (candle_5m.close_time - candle_5m.open_time).total_seconds()
        assert time_diff_5m == 300  # 5 minutes

        # 1h candle
        candle_1h = provider._parse_candle("tBTCUSD", "1h", candle_data)
        time_diff_1h = (candle_1h.close_time - candle_1h.open_time).total_seconds()
        assert time_diff_1h == 3600  # 1 hour

    def test_start(self):
        """Test starting the provider."""
        provider = BitfinexWebSocketCandleProvider()
        provider.ws_client = Mock()

        provider.start()

        provider.ws_client.start.assert_called_once()

    def test_stop(self):
        """Test stopping the provider."""
        provider = BitfinexWebSocketCandleProvider()
        provider.ws_client = Mock()

        provider.stop()

        provider.ws_client.stop.assert_called_once()

    def test_is_connected(self):
        """Test checking connection status."""
        provider = BitfinexWebSocketCandleProvider()
        provider.ws_client = Mock()
        provider.ws_client.is_connected.return_value = True

        assert provider.is_connected() is True
        provider.ws_client.is_connected.assert_called_once()

    def test_get_candle_updates_empty(self):
        """Test getting candle updates when queue is empty."""
        provider = BitfinexWebSocketCandleProvider()

        candles = provider.get_candle_updates(timeout=0.1)

        assert len(candles) == 0

    def test_get_candle_updates_with_data(self):
        """Test getting candle updates from queue."""
        provider = BitfinexWebSocketCandleProvider()

        # Add candles to queue
        candle1 = Candle(
            symbol="BTCUSD",
            exchange="bitfinex",
            timeframe="1m",
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("10.0"),
        )
        candle2 = Candle(
            symbol="BTCUSD",
            exchange="bitfinex",
            timeframe="1m",
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            open=Decimal("50050"),
            high=Decimal("50150"),
            low=Decimal("50000"),
            close=Decimal("50100"),
            volume=Decimal("8.0"),
        )

        provider.candle_queue.put(candle1)
        provider.candle_queue.put(candle2)

        candles = provider.get_candle_updates(timeout=0.1)

        assert len(candles) == 2
        assert candles[0] == candle1
        assert candles[1] == candle2

    def test_fetch_candles_compatibility(self):
        """Test fetch_candles() exists for CandleProvider compatibility."""
        provider = BitfinexWebSocketCandleProvider()

        # Just verify the method exists and has correct signature
        import inspect

        sig = inspect.signature(provider.fetch_candles)
        params = list(sig.parameters.keys())

        assert "symbol" in params
        assert "timeframe" in params
        assert "limit" in params


class TestBitfinexWebSocketCandleProviderIntegration:
    """Integration tests requiring actual WebSocket connection."""

    @pytest.mark.skip(reason="Requires live WebSocket connection")
    def test_live_subscription(self):
        """
        Integration test with live Bitfinex WebSocket.

        Skipped by default to avoid network dependencies in CI.
        Run manually to test against live API.
        """
        provider = BitfinexWebSocketCandleProvider()
        received_candles = []

        def on_candle(candle):
            received_candles.append(candle)

        provider.subscribe("BTCUSD", "1m", on_candle)
        provider.start()

        # Wait for candles
        time.sleep(10)

        provider.stop()

        # Should have received at least one candle
        assert len(received_candles) > 0

        # Verify candle is correct type
        candle = received_candles[0]
        assert isinstance(candle, Candle)
        assert candle.symbol == "BTCUSD"
        assert candle.exchange == "bitfinex"
        assert candle.timeframe == "1m"
