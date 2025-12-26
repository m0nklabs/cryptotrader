"""Real-time candle streaming service using Bitfinex WebSocket.

This module provides Server-Sent Events (SSE) endpoints for streaming
live candle updates from Bitfinex to frontend clients.

Architecture:
- Single WebSocket connection to Bitfinex per symbol/timeframe
- In-memory broadcast to multiple SSE clients
- Automatic reconnection on disconnect
- Thread-safe subscription management
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from typing import Any, AsyncIterator

from core.market_data.websocket_provider import BitfinexWebSocketCandleProvider
from core.types import Candle

logger = logging.getLogger(__name__)

# Queue size for candle updates per subscriber
# This should be large enough to handle bursts of updates but not so large
# that it consumes excessive memory. 100 candles is sufficient for:
# - ~1.5 hours of 1m candles
# - Multiple concurrent candle updates during reconnection
SUBSCRIBER_QUEUE_SIZE = 100


class CandleStreamService:
    """
    Service for managing real-time candle streams.

    Maintains a single WebSocket connection to Bitfinex for each subscribed
    symbol/timeframe and broadcasts updates to multiple SSE clients.
    """

    def __init__(self):
        """Initialize the candle stream service."""
        self.providers: dict[str, BitfinexWebSocketCandleProvider] = {}
        self.subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self.lock = threading.Lock()
        self.latest_candles: dict[str, Candle] = {}  # key -> latest candle

    def _get_key(self, symbol: str, timeframe: str) -> str:
        """Generate subscription key."""
        return f"{symbol}:{timeframe}"

    def get_or_create_provider(self, symbol: str, timeframe: str) -> BitfinexWebSocketCandleProvider:
        """
        Get or create a WebSocket provider for the given symbol/timeframe.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSD')
            timeframe: Candle timeframe (e.g., '1m')

        Returns:
            WebSocket provider for the symbol/timeframe
        """
        key = self._get_key(symbol, timeframe)

        with self.lock:
            if key not in self.providers:
                logger.info(f"Creating new WebSocket provider for {key}")
                provider = BitfinexWebSocketCandleProvider()

                # Subscribe to candle updates
                def on_candle(candle: Candle) -> None:
                    """Callback for candle updates."""
                    self._broadcast_candle(key, candle)

                provider.subscribe(symbol, timeframe, on_candle)
                provider.start()

                self.providers[key] = provider

        return self.providers[key]

    def _broadcast_candle(self, key: str, candle: Candle) -> None:
        """
        Broadcast candle update to all subscribers.

        Args:
            key: Subscription key
            candle: New candle data
        """
        # Broadcast to all subscribers (thread-safe)
        with self.lock:
            # Update latest candle inside lock for thread safety
            self.latest_candles[key] = candle

            subscribers = self.subscribers.get(key, [])
            logger.debug(f"Broadcasting candle for {key} to {len(subscribers)} subscribers")

            for queue in subscribers:
                try:
                    # Use put_nowait to avoid blocking
                    queue.put_nowait(candle)
                except asyncio.QueueFull:
                    logger.warning("Queue full for subscriber, dropping candle update")

    async def subscribe(self, symbol: str, timeframe: str) -> AsyncIterator[dict[str, Any]]:
        """
        Subscribe to real-time candle updates via SSE.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSD')
            timeframe: Candle timeframe (e.g., '1m')

        Yields:
            Candle data as dictionaries
        """
        key = self._get_key(symbol, timeframe)

        # Ensure WebSocket provider exists
        self.get_or_create_provider(symbol, timeframe)

        # Create subscriber queue
        queue: asyncio.Queue[Candle] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)

        with self.lock:
            self.subscribers[key].append(queue)
            subscriber_count = len(self.subscribers[key])

        logger.info(f"New SSE subscriber for {key} (total: {subscriber_count})")

        try:
            # Send latest candle immediately if available
            with self.lock:
                latest = self.latest_candles.get(key)
            if latest:
                yield self._candle_to_dict(latest)

            # Stream updates
            while True:
                try:
                    # Wait for new candle with timeout
                    candle = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield self._candle_to_dict(candle)
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield {"type": "heartbeat", "timestamp": int(time.time() * 1000)}

        finally:
            # Clean up subscriber
            with self.lock:
                if queue in self.subscribers[key]:
                    self.subscribers[key].remove(queue)
                    remaining = len(self.subscribers[key])
                    logger.info(f"SSE subscriber disconnected from {key} (remaining: {remaining})")

                    # Stop WebSocket if no more subscribers
                    if remaining == 0 and key in self.providers:
                        logger.info(f"No more subscribers for {key}, stopping WebSocket")
                        self.providers[key].stop()
                        del self.providers[key]
                        # Clean up latest candle to avoid memory leak
                        if key in self.latest_candles:
                            del self.latest_candles[key]

    def _candle_to_dict(self, candle: Candle) -> dict[str, Any]:
        """
        Convert Candle object to dictionary for SSE transmission.

        Args:
            candle: Candle object

        Returns:
            Dictionary representation of candle
        """
        return {
            "type": "candle",
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "t": int(candle.open_time.timestamp() * 1000),
            "o": float(candle.open),
            "h": float(candle.high),
            "l": float(candle.low),
            "c": float(candle.close),
            "v": float(candle.volume),
        }

    def get_connection_status(self) -> dict[str, Any]:
        """
        Get current connection status.

        Returns:
            Dictionary with connection information
        """
        with self.lock:
            return {
                "active_streams": len(self.providers),
                "total_subscribers": sum(len(subs) for subs in self.subscribers.values()),
                "streams": [
                    {
                        "key": key,
                        "subscribers": len(self.subscribers.get(key, [])),
                        "connected": provider.is_connected(),
                    }
                    for key, provider in self.providers.items()
                ],
            }


# Global singleton instance
_candle_stream_service: CandleStreamService | None = None


def get_candle_stream_service() -> CandleStreamService:
    """Get or create the global candle stream service instance."""
    global _candle_stream_service
    if _candle_stream_service is None:
        _candle_stream_service = CandleStreamService()
    return _candle_stream_service
