"""
Bitfinex WebSocket Candle Provider
===================================

Real-time candle provider using Bitfinex WebSocket API.
Implements CandleProvider interface for streaming candle updates.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional, Sequence

from cex.bitfinex.api.websocket_client import BitfinexWebSocket
from core.types import Candle, Timeframe

logger = logging.getLogger(__name__)


class BitfinexWebSocketCandleProvider:
    """
    WebSocket-based candle provider for Bitfinex.

    Provides real-time candle updates via WebSocket streaming.
    Can be used for live monitoring and real-time signal generation.
    """

    # Map internal timeframes to Bitfinex API format
    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1D",
    }

    def __init__(self, exchange: str = "bitfinex"):
        """
        Initialize WebSocket candle provider.

        Args:
            exchange: Exchange identifier (default: "bitfinex")
        """
        self.exchange = exchange
        self.ws_client = BitfinexWebSocket()
        self.candle_queue: queue.Queue = queue.Queue()
        self.subscriptions: dict[str, bool] = {}  # key -> subscribed
        self.lock = threading.Lock()

    def subscribe(self, symbol: str, timeframe: Timeframe, callback: Optional[Callable[[Candle], None]] = None) -> None:
        """
        Subscribe to real-time candle updates.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSD' or 'tBTCUSD')
            timeframe: Candle timeframe
            callback: Optional callback function to receive candles

        Example:
            >>> provider = BitfinexWebSocketCandleProvider()
            >>> def on_candle(candle):
            ...     print(f"New candle: {candle.close}")
            >>> provider.subscribe('BTCUSD', '1m', on_candle)
            >>> provider.start()
        """
        # Normalize symbol
        if not symbol.startswith("t"):
            symbol = "t" + symbol

        # Map timeframe
        api_timeframe = self.TIMEFRAME_MAP.get(timeframe)
        if not api_timeframe:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        key = f"{symbol}:{timeframe}"

        # Create callback wrapper
        def candle_callback(candle_data: dict) -> None:
            """Convert raw candle data to Candle object."""
            try:
                candle = self._parse_candle(symbol, timeframe, candle_data)

                # Add to queue for polling
                self.candle_queue.put(candle)

                # Call user callback if provided
                if callback:
                    callback(candle)

            except Exception as e:
                logger.error(f"Error processing candle for {key}: {e}")

        # Subscribe to WebSocket
        self.ws_client.subscribe_candles(symbol, api_timeframe, candle_callback)

        with self.lock:
            self.subscriptions[key] = True

        logger.info(f"Subscribed to {key}")

    def _parse_candle(self, symbol: str, timeframe: Timeframe, data: dict) -> Candle:
        """
        Parse raw candle data into Candle object.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            data: Raw candle data dict

        Returns:
            Candle object
        """
        # Convert timestamp from milliseconds to datetime
        timestamp_ms = data["timestamp"]
        open_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

        # Calculate close time based on timeframe
        timeframe_seconds = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        close_time = datetime.fromtimestamp(timestamp_ms / 1000 + timeframe_seconds.get(timeframe, 60), tz=timezone.utc)

        # Remove 't' prefix from symbol for consistency
        clean_symbol = symbol[1:] if symbol.startswith("t") else symbol

        return Candle(
            symbol=clean_symbol,
            exchange=self.exchange,
            timeframe=timeframe,
            open_time=open_time,
            close_time=close_time,
            open=Decimal(str(data["open"])),
            high=Decimal(str(data["high"])),
            low=Decimal(str(data["low"])),
            close=Decimal(str(data["close"])),
            volume=Decimal(str(data["volume"])),
        )

    def start(self) -> None:
        """
        Start the WebSocket client.

        Must be called after subscribing to symbols.
        """
        self.ws_client.start()
        logger.info("WebSocket candle provider started")

    def stop(self) -> None:
        """
        Stop the WebSocket client.
        """
        self.ws_client.stop()
        logger.info("WebSocket candle provider stopped")

    def get_candle_updates(self, timeout: float = 1.0) -> Sequence[Candle]:
        """
        Get all pending candle updates from the queue.

        Args:
            timeout: Maximum time to wait for first candle (seconds)

        Returns:
            List of candles received since last call

        Example:
            >>> provider.subscribe('BTCUSD', '1m')
            >>> provider.start()
            >>> time.sleep(5)
            >>> candles = provider.get_candle_updates()
            >>> for candle in candles:
            ...     print(f"Price: {candle.close}")
        """
        candles = []

        try:
            # Wait for first candle with timeout
            candle = self.candle_queue.get(timeout=timeout)
            candles.append(candle)

            # Get all remaining candles without blocking
            while True:
                try:
                    candle = self.candle_queue.get_nowait()
                    candles.append(candle)
                except queue.Empty:
                    break

        except queue.Empty:
            pass

        return candles

    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self.ws_client.is_connected()

    # CandleProvider interface compatibility
    def fetch_candles(self, *, symbol: str, timeframe: Timeframe, limit: int) -> Sequence[Candle]:
        """
        Fetch candles (compatibility method for CandleProvider interface).

        Note: This is not the primary use case for WebSocket provider.
        For batch fetching, use REST API-based providers instead.

        This method subscribes and waits for updates, which is inefficient
        for historical data fetching.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            limit: Number of candles (ignored, returns available updates)

        Returns:
            Available candle updates
        """
        logger.warning(
            "fetch_candles() called on WebSocket provider. "
            "This is intended for streaming, not batch fetching. "
            "Consider using REST-based provider for historical data."
        )

        # Subscribe if not already subscribed
        key = f"{symbol}:{timeframe}"
        with self.lock:
            if key not in self.subscriptions:
                self.subscribe(symbol, timeframe)

                # Start if not already running
                if not self.is_connected():
                    self.start()

                # Wait briefly for initial data
                time.sleep(2)

        # Return available updates
        return self.get_candle_updates(timeout=0.1)
