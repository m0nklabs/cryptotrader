from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import websockets

logger = logging.getLogger(__name__)

PriceCallback = Callable[[dict[str, object]], Awaitable[None]]
StatusCallback = Callable[[str], Awaitable[None]]


def _normalize_bitfinex_symbol(symbol: str) -> str:
    if symbol.startswith("t"):
        return symbol
    return f"t{symbol}"


class BitfinexWebSocketClient:
    """Bitfinex WebSocket client for live prices."""

    ws_url = "wss://api-pub.bitfinex.com/ws/2"

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

        backoff = 1.0
        while not stop_event.is_set():
            try:
                await on_status("connecting")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    await on_status("connected")
                    backoff = 1.0

                    channel_map: dict[int, str] = {}
                    for symbol in sorted(symbols):
                        await ws.send(
                            json.dumps(
                                {
                                    "event": "subscribe",
                                    "channel": "ticker",
                                    "symbol": _normalize_bitfinex_symbol(symbol),
                                }
                            )
                        )

                    while not stop_event.is_set():
                        message = await ws.recv()
                        data = json.loads(message)

                        if isinstance(data, dict):
                            if data.get("event") == "subscribed":
                                chan_id = data.get("chanId")
                                symbol = data.get("symbol")
                                if isinstance(chan_id, int) and isinstance(symbol, str):
                                    channel_map[chan_id] = symbol
                            continue

                        if isinstance(data, list) and len(data) >= 2:
                            channel_id = data[0]
                            payload = data[1]
                            if payload == "hb":
                                continue
                            if not isinstance(payload, list) or len(payload) < 7:
                                continue
                            raw_symbol = channel_map.get(channel_id)
                            if not raw_symbol:
                                continue
                            symbol = raw_symbol[1:] if raw_symbol.startswith("t") else raw_symbol
                            last_price = payload[6]
                            await on_price(
                                {
                                    "type": "price",
                                    "exchange": "bitfinex",
                                    "symbol": symbol,
                                    "price": float(last_price),
                                    "timestamp": int(time.time() * 1000),
                                }
                            )

                await on_status("disconnected")
            except Exception as exc:
                logger.warning("Bitfinex WebSocket error: %s", exc)
                await on_status("disconnected")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
