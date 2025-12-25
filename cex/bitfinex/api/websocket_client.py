"""
Bitfinex WebSocket Client - Real-time Market Data
==================================================

WebSocket client for Bitfinex API v2 providing real-time candle updates.

Features:
- Subscribe to candle updates for specific symbols and timeframes
- Automatic reconnection on disconnection
- Callback-based event handling
- Thread-safe operation

Usage:
    from cex.bitfinex.api.websocket_client import BitfinexWebSocket

    def on_candle(candle_data):
        print(f"New candle: {candle_data}")

    ws = BitfinexWebSocket()
    ws.subscribe_candles("tBTCUSD", "1m", on_candle)
    ws.start()

    # ... do other work ...

    ws.stop()
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

import websocket

logger = logging.getLogger(__name__)


class BitfinexWebSocket:
    """
    Bitfinex WebSocket v2 Client for real-time market data.

    Connects to Bitfinex WebSocket API and manages subscriptions
    to candle updates.
    """

    WS_URL = "wss://api-pub.bitfinex.com/ws/2"

    def __init__(self, reconnect: bool = True, reconnect_interval: int = 5):
        """
        Initialize Bitfinex WebSocket client.

        Args:
            reconnect: Whether to automatically reconnect on disconnection
            reconnect_interval: Seconds to wait before reconnecting
        """
        self.ws: Optional[websocket.WebSocketApp] = None
        self.reconnect = reconnect
        self.reconnect_interval = reconnect_interval
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Subscription management
        self.subscriptions: Dict[int, Dict[str, Any]] = {}  # channel_id -> subscription info
        self.pending_subscriptions: list[Dict[str, Any]] = []  # subscriptions to restore on reconnect
        self.channel_callbacks: Dict[int, Callable] = {}  # channel_id -> callback

        # Thread safety
        self.lock = threading.Lock()

    def subscribe_candles(self, symbol: str, timeframe: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Subscribe to candle updates for a symbol and timeframe.

        Args:
            symbol: Trading pair symbol (e.g., 'tBTCUSD')
            timeframe: Candle timeframe (1m, 5m, 15m, 30m, 1h, 3h, 6h, 12h, 1D, 7D, 14D, 1M)
            callback: Function to call when candle update is received
                      Receives dict with: timestamp, open, close, high, low, volume

        Example:
            >>> def on_candle(data):
            ...     print(f"BTC price: {data['close']}")
            >>> ws.subscribe_candles('tBTCUSD', '1m', on_candle)
        """
        # Ensure symbol starts with 't'
        if not symbol.startswith("t"):
            symbol = "t" + symbol

        key = f"trade:{timeframe}:{symbol}"

        subscription = {
            "event": "subscribe",
            "channel": "candles",
            "key": key,
            "symbol": symbol,
            "timeframe": timeframe,
            "callback": callback,
        }

        with self.lock:
            self.pending_subscriptions.append(subscription)

        # If already connected, send subscription immediately
        if self.ws and self.running:
            self._send_subscription(subscription)

    def _send_subscription(self, subscription: Dict[str, Any]) -> None:
        """Send subscription request to WebSocket."""
        msg = {"event": subscription["event"], "channel": subscription["channel"], "key": subscription["key"]}

        if self.ws:
            try:
                self.ws.send(json.dumps(msg))
                logger.info(f"Sent subscription: {msg}")
            except Exception as e:
                logger.error(f"Failed to send subscription: {e}")

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)

            # Handle info/event messages
            if isinstance(data, dict):
                event = data.get("event")

                if event == "info":
                    logger.info(f"WebSocket info: {data}")

                elif event == "subscribed":
                    # Store channel subscription
                    channel_id = data.get("chanId")
                    key = data.get("key", "")

                    with self.lock:
                        # Find matching pending subscription
                        for sub in self.pending_subscriptions:
                            if sub["key"] == key:
                                self.subscriptions[channel_id] = sub
                                self.channel_callbacks[channel_id] = sub["callback"]
                                logger.info(f"Subscribed to {key} on channel {channel_id}")
                                break

                elif event == "error":
                    logger.error(f"WebSocket error: {data}")

                return

            # Handle candle data (array format)
            if isinstance(data, list) and len(data) >= 2:
                channel_id = data[0]

                # Skip heartbeat messages
                if data[1] == "hb":
                    return

                # Get callback for this channel
                callback = self.channel_callbacks.get(channel_id)
                if not callback:
                    return

                # Parse candle data
                candle_raw = data[1]

                # Handle snapshot (array of candles)
                if isinstance(candle_raw, list) and len(candle_raw) > 0:
                    if isinstance(candle_raw[0], list):
                        # Snapshot: [[MTS, OPEN, CLOSE, HIGH, LOW, VOLUME], ...]
                        for candle in candle_raw:
                            self._process_candle(candle, callback)
                    else:
                        # Single update: [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]
                        self._process_candle(candle_raw, callback)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _process_candle(self, candle: list, callback: Callable) -> None:
        """Process a single candle and invoke callback."""
        try:
            if len(candle) >= 6:
                candle_data = {
                    "timestamp": candle[0],
                    "open": float(candle[1]),
                    "close": float(candle[2]),
                    "high": float(candle[3]),
                    "low": float(candle[4]),
                    "volume": float(candle[5]),
                }
                callback(candle_data)
        except Exception as e:
            logger.error(f"Error in candle callback: {e}")

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        """Handle WebSocket errors."""
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws: websocket.WebSocketApp, close_status_code: int, close_msg: str) -> None:
        """Handle WebSocket closure."""
        logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")

        if self.reconnect and self.running:
            logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
            time.sleep(self.reconnect_interval)
            if self.running:
                self._connect()

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        """Handle WebSocket connection opening."""
        logger.info("WebSocket connected")

        # Restore all pending subscriptions
        with self.lock:
            for subscription in self.pending_subscriptions:
                self._send_subscription(subscription)

    def _connect(self) -> None:
        """Establish WebSocket connection."""
        self.ws = websocket.WebSocketApp(
            self.WS_URL,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )

        # Run WebSocket in current thread (will be called from thread)
        self.ws.run_forever()

    def start(self) -> None:
        """
        Start the WebSocket client in a background thread.

        Example:
            >>> ws = BitfinexWebSocket()
            >>> ws.subscribe_candles('tBTCUSD', '1m', on_candle)
            >>> ws.start()
        """
        if self.running:
            logger.warning("WebSocket already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._connect, daemon=True)
        self.thread.start()
        logger.info("WebSocket client started")

    def stop(self) -> None:
        """
        Stop the WebSocket client.

        Example:
            >>> ws.stop()
        """
        logger.info("Stopping WebSocket client...")
        self.running = False

        if self.ws:
            self.ws.close()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        logger.info("WebSocket client stopped")

    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self.ws is not None and self.running
