"""WebSocket client for real-time Bitfinex candle updates."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import websocket

from core.types import Candle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandleUpdate:
    """Real-time candle update from WebSocket."""

    exchange: str
    symbol: str
    timeframe: str
    candle: Candle


class BitfinexWebSocketManager:
    """Manages WebSocket connection to Bitfinex for real-time candle updates.

    Supports subscribing to multiple symbol/timeframe pairs and provides
    callbacks when new candles are received.
    """

    def __init__(self, callback: Callable[[CandleUpdate], None] | None = None):
        """Initialize WebSocket manager.

        Args:
            callback: Function called when a new candle update is received.
        """
        self._callback = callback
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._subscriptions: dict[str, dict[str, Any]] = {}  # key -> {symbol, timeframe, chan_id}
        self._channel_map: dict[int, str] = {}  # chan_id -> subscription_key
        self._lock = threading.Lock()
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    def _subscription_key(self, symbol: str, timeframe: str) -> str:
        """Generate unique key for symbol/timeframe pair."""
        return f"{symbol}:{timeframe}"

    def subscribe(self, symbol: str, timeframe: str) -> None:
        """Subscribe to candle updates for a symbol/timeframe pair.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSD")
            timeframe: Candle timeframe (e.g., "1m")
        """
        key = self._subscription_key(symbol, timeframe)
        with self._lock:
            if key not in self._subscriptions:
                self._subscriptions[key] = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "chan_id": None,
                }
                logger.info(f"Added subscription for {symbol} {timeframe}")

                # If already connected, send subscribe message
                if self._ws and self._running:
                    self._send_subscribe(symbol, timeframe)

    def unsubscribe(self, symbol: str, timeframe: str) -> None:
        """Unsubscribe from candle updates.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
        """
        key = self._subscription_key(symbol, timeframe)
        with self._lock:
            if key in self._subscriptions:
                sub = self._subscriptions[key]
                chan_id = sub.get("chan_id")

                # Send unsubscribe if connected
                if self._ws and chan_id and self._running:
                    try:
                        self._ws.send(json.dumps({"event": "unsubscribe", "chanId": chan_id}))
                    except Exception as exc:
                        logger.warning(f"Failed to send unsubscribe: {exc}")

                # Clean up
                if chan_id:
                    self._channel_map.pop(chan_id, None)
                self._subscriptions.pop(key)
                logger.info(f"Removed subscription for {symbol} {timeframe}")

    def _send_subscribe(self, symbol: str, timeframe: str) -> None:
        """Send subscribe message to WebSocket."""
        if not self._ws:
            return

        # Normalize symbol for Bitfinex (prefix with 't')
        bitfinex_symbol = symbol if symbol.startswith("t") else f"t{symbol}"

        # Map timeframe to Bitfinex format
        timeframe_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1D",
        }
        bitfinex_timeframe = timeframe_map.get(timeframe, timeframe)

        subscribe_msg = {
            "event": "subscribe",
            "channel": "candles",
            "key": f"trade:{bitfinex_timeframe}:{bitfinex_symbol}",
        }

        try:
            self._ws.send(json.dumps(subscribe_msg))
            logger.debug(f"Sent subscribe for {symbol} {timeframe}")
        except Exception as exc:
            logger.error(f"Failed to send subscribe: {exc}")

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)

            # Handle subscription confirmation
            if isinstance(data, dict) and data.get("event") == "subscribed":
                chan_id = data.get("chanId")
                key = data.get("key", "")

                # Parse key: "trade:1m:tBTCUSD"
                parts = key.split(":")
                if len(parts) == 3 and chan_id:
                    timeframe_raw = parts[1]
                    symbol_raw = parts[2]

                    # Normalize back from Bitfinex format
                    symbol = symbol_raw[1:] if symbol_raw.startswith("t") else symbol_raw
                    timeframe_map_reverse = {
                        "1m": "1m",
                        "5m": "5m",
                        "15m": "15m",
                        "1h": "1h",
                        "4h": "4h",
                        "1D": "1d",
                    }
                    timeframe = timeframe_map_reverse.get(timeframe_raw, timeframe_raw)

                    subscription_key = self._subscription_key(symbol, timeframe)
                    with self._lock:
                        if subscription_key in self._subscriptions:
                            self._subscriptions[subscription_key]["chan_id"] = chan_id
                            self._channel_map[chan_id] = subscription_key
                            logger.info(f"Subscription confirmed: {symbol} {timeframe} (channel {chan_id})")

            # Handle candle updates
            elif isinstance(data, list) and len(data) >= 2:
                chan_id = data[0]
                payload = data[1]

                # Skip heartbeat messages
                if payload == "hb":
                    return

                # Get subscription info
                subscription_key = self._channel_map.get(chan_id)
                if not subscription_key:
                    return

                with self._lock:
                    sub = self._subscriptions.get(subscription_key)
                    if not sub:
                        return

                    symbol = sub["symbol"]
                    timeframe = sub["timeframe"]

                # Parse candle data: [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]
                if isinstance(payload, list) and len(payload) >= 6:
                    try:
                        candle = self._parse_candle(payload, symbol, timeframe)
                        if candle and self._callback:
                            update = CandleUpdate(
                                exchange="bitfinex",
                                symbol=symbol,
                                timeframe=timeframe,
                                candle=candle,
                            )
                            self._callback(update)
                    except Exception as exc:
                        logger.error(f"Failed to parse candle: {exc}")

        except Exception as exc:
            logger.error(f"Error handling message: {exc}")

    def _parse_candle(self, data: list[Any], symbol: str, timeframe: str) -> Candle | None:
        """Parse candle data from WebSocket message.

        Args:
            data: [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]
            symbol: Trading pair symbol
            timeframe: Candle timeframe

        Returns:
            Candle object or None if parsing fails
        """
        try:
            mts = int(data[0])
            open_time = datetime.fromtimestamp(mts / 1000, tz=timezone.utc)

            # Calculate close time based on timeframe
            timeframe_deltas = {
                "1m": 60,
                "5m": 300,
                "15m": 900,
                "1h": 3600,
                "4h": 14400,
                "1d": 86400,
            }
            delta_seconds = timeframe_deltas.get(timeframe, 60)
            close_time = datetime.fromtimestamp((mts / 1000) + delta_seconds, tz=timezone.utc)

            return Candle(
                exchange="bitfinex",
                symbol=symbol,
                timeframe=timeframe,  # type: ignore[arg-type]
                open_time=open_time,
                close_time=close_time,
                open=Decimal(str(data[1])),
                close=Decimal(str(data[2])),
                high=Decimal(str(data[3])),
                low=Decimal(str(data[4])),
                volume=Decimal(str(data[5])),
            )
        except Exception as exc:
            logger.error(f"Failed to parse candle data: {exc}")
            return None

    def _on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        """Handle WebSocket error."""
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws: websocket.WebSocketApp, close_status_code: int, close_msg: str) -> None:
        """Handle WebSocket close."""
        logger.info(f"WebSocket closed: {close_status_code} {close_msg}")

        # Attempt reconnect if still running
        if self._running:
            logger.info(f"Reconnecting in {self._reconnect_delay}s...")
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
            if self._running:
                self._connect()

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        """Handle WebSocket open."""
        logger.info("WebSocket connected")
        self._reconnect_delay = 1.0

        # Resubscribe to all active subscriptions
        with self._lock:
            subs = list(self._subscriptions.values())

        for sub in subs:
            self._send_subscribe(sub["symbol"], sub["timeframe"])

    def _connect(self) -> None:
        """Establish WebSocket connection."""
        self._ws = websocket.WebSocketApp(
            "wss://api-pub.bitfinex.com/ws/2",
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )

        # Run in background thread
        def run():
            while self._running:
                try:
                    self._ws.run_forever(ping_interval=30, ping_timeout=10)
                except Exception as exc:
                    logger.error(f"WebSocket run_forever error: {exc}")
                    if self._running:
                        time.sleep(self._reconnect_delay)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def start(self) -> None:
        """Start WebSocket connection."""
        if self._running:
            logger.warning("WebSocket manager already running")
            return

        self._running = True
        self._connect()
        logger.info("WebSocket manager started")

    def stop(self) -> None:
        """Stop WebSocket connection."""
        if not self._running:
            return

        self._running = False

        if self._ws:
            self._ws.close()
            self._ws = None

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.info("WebSocket manager stopped")
