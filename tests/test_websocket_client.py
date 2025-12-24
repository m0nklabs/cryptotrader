"""
Tests for Bitfinex WebSocket Client
====================================

Tests WebSocket client functionality with mocked WebSocket connection.
"""

import json
import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from cex.bitfinex.api.websocket_client import BitfinexWebSocket


class TestBitfinexWebSocket:
    """Test suite for BitfinexWebSocket."""
    
    def test_initialization(self):
        """Test WebSocket client initialization."""
        ws = BitfinexWebSocket()
        
        assert ws.WS_URL == "wss://api-pub.bitfinex.com/ws/2"
        assert ws.reconnect is True
        assert ws.reconnect_interval == 5
        assert ws.running is False
        assert len(ws.subscriptions) == 0
        assert len(ws.pending_subscriptions) == 0
    
    def test_subscribe_candles(self):
        """Test subscribing to candle updates."""
        ws = BitfinexWebSocket()
        callback = Mock()
        
        ws.subscribe_candles('BTCUSD', '1m', callback)
        
        assert len(ws.pending_subscriptions) == 1
        sub = ws.pending_subscriptions[0]
        assert sub['symbol'] == 'tBTCUSD'
        assert sub['timeframe'] == '1m'
        assert sub['key'] == 'trade:1m:tBTCUSD'
        assert sub['callback'] == callback
    
    def test_subscribe_candles_with_t_prefix(self):
        """Test subscribing with symbol already having 't' prefix."""
        ws = BitfinexWebSocket()
        callback = Mock()
        
        ws.subscribe_candles('tETHUSD', '5m', callback)
        
        sub = ws.pending_subscriptions[0]
        assert sub['symbol'] == 'tETHUSD'
        assert sub['key'] == 'trade:5m:tETHUSD'
    
    def test_on_message_subscribed_event(self):
        """Test handling subscribed event."""
        ws = BitfinexWebSocket()
        callback = Mock()
        
        # Add pending subscription
        ws.subscribe_candles('tBTCUSD', '1m', callback)
        
        # Simulate subscribed event
        message = json.dumps({
            "event": "subscribed",
            "channel": "candles",
            "chanId": 12345,
            "key": "trade:1m:tBTCUSD"
        })
        
        ws._on_message(None, message)
        
        # Check subscription was stored
        assert 12345 in ws.subscriptions
        assert 12345 in ws.channel_callbacks
        assert ws.channel_callbacks[12345] == callback
    
    def test_on_message_candle_update(self):
        """Test handling candle update."""
        ws = BitfinexWebSocket()
        callback = Mock()
        
        # Set up subscription
        ws.channel_callbacks[12345] = callback
        
        # Simulate candle update
        # Format: [CHANNEL_ID, [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]]
        message = json.dumps([
            12345,
            [1640000000000, 50000.0, 50100.0, 50200.0, 49900.0, 10.5]
        ])
        
        ws._on_message(None, message)
        
        # Check callback was called
        callback.assert_called_once()
        candle_data = callback.call_args[0][0]
        
        assert candle_data['timestamp'] == 1640000000000
        assert candle_data['open'] == 50000.0
        assert candle_data['close'] == 50100.0
        assert candle_data['high'] == 50200.0
        assert candle_data['low'] == 49900.0
        assert candle_data['volume'] == 10.5
    
    def test_on_message_candle_snapshot(self):
        """Test handling candle snapshot (multiple candles)."""
        ws = BitfinexWebSocket()
        callback = Mock()
        
        # Set up subscription
        ws.channel_callbacks[12345] = callback
        
        # Simulate candle snapshot
        message = json.dumps([
            12345,
            [
                [1640000000000, 50000.0, 50100.0, 50200.0, 49900.0, 10.5],
                [1640000060000, 50100.0, 50150.0, 50200.0, 50000.0, 8.3]
            ]
        ])
        
        ws._on_message(None, message)
        
        # Check callback was called twice
        assert callback.call_count == 2
    
    def test_on_message_heartbeat(self):
        """Test heartbeat messages are ignored."""
        ws = BitfinexWebSocket()
        callback = Mock()
        
        ws.channel_callbacks[12345] = callback
        
        # Simulate heartbeat
        message = json.dumps([12345, "hb"])
        
        ws._on_message(None, message)
        
        # Callback should not be called
        callback.assert_not_called()
    
    def test_on_message_info_event(self):
        """Test info event handling."""
        ws = BitfinexWebSocket()
        
        message = json.dumps({
            "event": "info",
            "version": 2,
            "platform": {
                "status": 1
            }
        })
        
        # Should not raise exception
        ws._on_message(None, message)
    
    def test_on_message_error_event(self):
        """Test error event handling."""
        ws = BitfinexWebSocket()
        
        message = json.dumps({
            "event": "error",
            "msg": "Unknown error",
            "code": 10000
        })
        
        # Should not raise exception
        ws._on_message(None, message)
    
    def test_is_connected_when_not_started(self):
        """Test is_connected returns False when not started."""
        ws = BitfinexWebSocket()
        assert ws.is_connected() is False
    
    def test_is_connected_when_running(self):
        """Test is_connected returns True when running."""
        ws = BitfinexWebSocket()
        ws.running = True
        ws.ws = Mock()
        
        assert ws.is_connected() is True
    
    @patch('cex.bitfinex.api.websocket_client.websocket.WebSocketApp')
    def test_start_creates_websocket(self, mock_ws_app):
        """Test start() creates WebSocket connection."""
        ws = BitfinexWebSocket()
        
        # Mock WebSocketApp
        mock_instance = Mock()
        mock_ws_app.return_value = mock_instance
        
        ws.start()
        
        # Give thread time to start
        time.sleep(0.1)
        
        assert ws.running is True
        assert ws.thread is not None
        
        # Cleanup
        ws.stop()
    
    def test_stop_sets_running_false(self):
        """Test stop() sets running to False."""
        ws = BitfinexWebSocket()
        ws.running = True
        ws.ws = Mock()
        
        ws.stop()
        
        assert ws.running is False


class TestBitfinexWebSocketIntegration:
    """Integration tests requiring actual WebSocket connection."""
    
    @pytest.mark.skip(reason="Requires live WebSocket connection")
    def test_live_candle_subscription(self):
        """
        Integration test with live Bitfinex WebSocket.
        
        Skipped by default to avoid network dependencies in CI.
        Run manually to test against live API.
        """
        ws = BitfinexWebSocket()
        received_candles = []
        
        def on_candle(candle_data):
            received_candles.append(candle_data)
        
        ws.subscribe_candles('tBTCUSD', '1m', on_candle)
        ws.start()
        
        # Wait for some candles
        time.sleep(10)
        
        ws.stop()
        
        # Should have received at least one candle update
        assert len(received_candles) > 0
        
        # Verify candle structure
        candle = received_candles[0]
        assert 'timestamp' in candle
        assert 'open' in candle
        assert 'close' in candle
        assert 'high' in candle
        assert 'low' in candle
        assert 'volume' in candle
