"""Tests for Bitfinex WebSocket manager."""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import Mock, patch

from core.market_data.bitfinex_websocket import BitfinexWebSocketManager, CandleUpdate


class TestBitfinexWebSocketManager:
    """Test suite for BitfinexWebSocketManager."""

    def test_subscription_key_generation(self):
        """Test that subscription keys are generated correctly."""
        manager = BitfinexWebSocketManager()
        key = manager._subscription_key("BTCUSD", "1m")
        assert key == "BTCUSD:1m"

    def test_subscribe_adds_subscription(self):
        """Test that subscribe adds a new subscription."""
        manager = BitfinexWebSocketManager()
        manager.subscribe("BTCUSD", "1m")

        key = manager._subscription_key("BTCUSD", "1m")
        assert key in manager._subscriptions
        assert manager._subscriptions[key]["symbol"] == "BTCUSD"
        assert manager._subscriptions[key]["timeframe"] == "1m"

    def test_subscribe_does_not_duplicate(self):
        """Test that subscribing twice to the same pair doesn't create duplicates."""
        manager = BitfinexWebSocketManager()
        manager.subscribe("BTCUSD", "1m")
        manager.subscribe("BTCUSD", "1m")

        assert len(manager._subscriptions) == 1

    def test_unsubscribe_removes_subscription(self):
        """Test that unsubscribe removes a subscription."""
        manager = BitfinexWebSocketManager()
        manager.subscribe("BTCUSD", "1m")
        manager.unsubscribe("BTCUSD", "1m")

        key = manager._subscription_key("BTCUSD", "1m")
        assert key not in manager._subscriptions

    def test_parse_candle_valid_data(self):
        """Test parsing valid candle data."""
        manager = BitfinexWebSocketManager()

        # [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]
        data = [1703001600000, 42000.0, 42100.0, 42200.0, 41900.0, 100.5]
        candle = manager._parse_candle(data, "BTCUSD", "1m")

        assert candle is not None
        assert candle.symbol == "BTCUSD"
        assert candle.timeframe == "1m"
        assert candle.open == Decimal("42000.0")
        assert candle.close == Decimal("42100.0")
        assert candle.high == Decimal("42200.0")
        assert candle.low == Decimal("41900.0")
        assert candle.volume == Decimal("100.5")

    def test_parse_candle_invalid_data(self):
        """Test parsing invalid candle data returns None."""
        manager = BitfinexWebSocketManager()

        # Invalid data (too few elements)
        data = [1703001600000, 42000.0]
        candle = manager._parse_candle(data, "BTCUSD", "1m")

        assert candle is None

    def test_callback_invoked_on_message(self):
        """Test that callback is invoked when a candle update is received."""
        callback = Mock()
        manager = BitfinexWebSocketManager(callback=callback)

        # Simulate subscription confirmation
        manager._subscriptions["BTCUSD:1m"] = {
            "symbol": "BTCUSD",
            "timeframe": "1m",
            "chan_id": 123,
        }
        manager._channel_map[123] = "BTCUSD:1m"

        # Simulate candle update message
        # [CHANNEL_ID, [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]]
        message = json.dumps([123, [1703001600000, 42000.0, 42100.0, 42200.0, 41900.0, 100.5]])

        manager._on_message(Mock(), message)

        # Verify callback was called
        assert callback.call_count == 1
        update = callback.call_args[0][0]
        assert isinstance(update, CandleUpdate)
        assert update.exchange == "bitfinex"
        assert update.symbol == "BTCUSD"
        assert update.timeframe == "1m"

    def test_on_message_handles_subscription_confirmation(self):
        """Test that subscription confirmation is processed correctly."""
        manager = BitfinexWebSocketManager()
        manager.subscribe("BTCUSD", "1m")

        # Simulate subscription confirmation message
        message = json.dumps({
            "event": "subscribed",
            "channel": "candles",
            "chanId": 123,
            "key": "trade:1m:tBTCUSD",
        })

        manager._on_message(Mock(), message)

        # Verify channel mapping
        assert manager._channel_map[123] == "BTCUSD:1m"
        assert manager._subscriptions["BTCUSD:1m"]["chan_id"] == 123

    def test_on_message_ignores_heartbeat(self):
        """Test that heartbeat messages are ignored."""
        callback = Mock()
        manager = BitfinexWebSocketManager(callback=callback)

        # Simulate heartbeat message
        message = json.dumps([123, "hb"])

        manager._on_message(Mock(), message)

        # Verify callback was not called
        assert callback.call_count == 0

    def test_start_sets_running_flag(self):
        """Test that start() sets the running flag."""
        manager = BitfinexWebSocketManager()

        with patch.object(manager, "_connect"):
            manager.start()
            assert manager._running is True

    def test_stop_clears_running_flag(self):
        """Test that stop() clears the running flag."""
        manager = BitfinexWebSocketManager()
        manager._running = True
        ws_mock = Mock()
        manager._ws = ws_mock

        manager.stop()

        assert manager._running is False
        ws_mock.close.assert_called_once()
        assert manager._ws is None

    def test_timeframe_mapping(self):
        """Test that timeframes are correctly mapped to Bitfinex format."""
        manager = BitfinexWebSocketManager()

        # Mock WebSocket
        manager._ws = Mock()

        # Test various timeframes
        test_cases = [
            ("1m", "1m"),
            ("5m", "5m"),
            ("15m", "15m"),
            ("1h", "1h"),
            ("4h", "4h"),
            ("1d", "1D"),
        ]

        for local_tf, bitfinex_tf in test_cases:
            manager._send_subscribe("BTCUSD", local_tf)

            # Verify correct format was sent
            call_args = manager._ws.send.call_args[0][0]
            msg = json.loads(call_args)
            assert f"trade:{bitfinex_tf}:tBTCUSD" in msg["key"]

    def test_symbol_normalization(self):
        """Test that symbols are correctly normalized with 't' prefix."""
        manager = BitfinexWebSocketManager()
        manager._ws = Mock()

        # Test with and without 't' prefix
        manager._send_subscribe("BTCUSD", "1m")
        call_args = manager._ws.send.call_args[0][0]
        msg = json.loads(call_args)
        assert "tBTCUSD" in msg["key"]

        manager._send_subscribe("tBTCUSD", "1m")
        call_args = manager._ws.send.call_args[0][0]
        msg = json.loads(call_args)
        assert "tBTCUSD" in msg["key"]
        # Should not have double prefix
        assert "ttBTCUSD" not in msg["key"]
