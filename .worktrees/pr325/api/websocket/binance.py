from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import websockets

from core.market_data.binance_backfill import _normalize_binance_symbol

logger = logging.getLogger(__name__)

PriceCallback = Callable[[dict[str, object]], Awaitable[None]]
StatusCallback = Callable[[str], Awaitable[None]]


class BinanceWebSocketClient:
    """Lightweight Binance WebSocket client for live prices."""

    base_url = "wss://stream.binance.com:9443/stream"

    async def stream_prices(
        self,
        *,
        symbols: set[str],
        on_price: PriceCallback,
        on_status: StatusCallback,
        stop_event: asyncio.Event,
    ) -> None:
        if not symbols:
            return

        symbol_map = {_normalize_binance_symbol(symbol): symbol for symbol in symbols}
        streams = "/".join(f"{symbol.lower()}@ticker" for symbol in sorted(symbol_map))
        url = f"{self.base_url}?streams={streams}"

        backoff = 1.0
        while not stop_event.is_set():
            try:
                await on_status("connecting")
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    await on_status("connected")
                    backoff = 1.0
                    async for message in ws:
                        if stop_event.is_set():
                            break
                        payload = json.loads(message)
                        data = payload.get("data", {})
                        symbol = data.get("s")
                        price = data.get("c")
                        event_time = data.get("E") or int(time.time() * 1000)
                        if symbol and price is not None:
                            canonical_symbol = symbol_map.get(str(symbol), str(symbol))
                            await on_price(
                                {
                                    "type": "price",
                                    "exchange": "binance",
                                    "symbol": canonical_symbol,
                                    "price": float(price),
                                    "timestamp": int(event_time),
                                }
                            )
                await on_status("disconnected")
            except Exception as exc:
                logger.warning("Binance WebSocket error: %s", exc)
                await on_status("disconnected")
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    logger.debug("Binance WebSocket backoff expired; retrying")
                backoff = min(backoff * 2, 30.0)
