from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.websocket.binance import BinanceWebSocketClient
from api.websocket.bitfinex import BitfinexWebSocketClient


class _FakeBinanceSocket:
    def __init__(self, messages: list[str]):
        self._messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


class _FakeBitfinexSocket:
    def __init__(self, messages: list[str]):
        self._messages = messages
        self.sent: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        await asyncio.sleep(0.01)
        return json.dumps([0, "hb"])


@pytest.mark.asyncio
async def test_binance_stream_prices_parses_message() -> None:
    messages = [
        json.dumps(
            {
                "stream": "btcusdt@ticker",
                "data": {"s": "BTCUSDT", "c": "50000.00", "E": 1700000000000},
            }
        )
    ]
    socket = _FakeBinanceSocket(messages)
    statuses: list[str] = []
    updates: list[dict[str, object]] = []
    stop_event = asyncio.Event()

    async def on_status(status: str) -> None:
        statuses.append(status)

    async def on_price(update: dict[str, object]) -> None:
        updates.append(update)
        stop_event.set()

    client = BinanceWebSocketClient()
    with patch("api.websocket.binance.websockets.connect", return_value=socket):
        await asyncio.wait_for(
            client.stream_prices(
                symbols={"BTCUSD"},
                on_price=on_price,
                on_status=on_status,
                stop_event=stop_event,
            ),
            timeout=1.0,
        )

    assert updates[0]["symbol"] == "BTCUSD"
    assert statuses[0] == "connecting"
    assert "connected" in statuses
    assert "disconnected" in statuses


@pytest.mark.asyncio
async def test_binance_stream_prices_reports_disconnect_on_error() -> None:
    statuses: list[str] = []
    stop_event = asyncio.Event()

    async def on_status(status: str) -> None:
        statuses.append(status)
        if status == "disconnected":
            stop_event.set()

    async def on_price(update: dict[str, object]) -> None:
        pass

    client = BinanceWebSocketClient()
    with (
        patch("api.websocket.binance.websockets.connect", side_effect=RuntimeError("boom")),
        patch("api.websocket.binance.asyncio.sleep", new=AsyncMock()),
    ):
        await asyncio.wait_for(
            client.stream_prices(
                symbols={"BTCUSDT"},
                on_price=on_price,
                on_status=on_status,
                stop_event=stop_event,
            ),
            timeout=1.0,
        )

    assert "disconnected" in statuses


@pytest.mark.asyncio
async def test_bitfinex_stream_prices_parses_message() -> None:
    messages = [
        json.dumps({"event": "subscribed", "chanId": 10, "symbol": "tBTCUSD"}),
        json.dumps([10, [0, 0, 0, 0, 0, 0, 50500, 0, 0, 0]]),
    ]
    socket = _FakeBitfinexSocket(messages)
    statuses: list[str] = []
    updates: list[dict[str, object]] = []
    stop_event = asyncio.Event()

    async def on_status(status: str) -> None:
        statuses.append(status)

    async def on_price(update: dict[str, object]) -> None:
        updates.append(update)
        stop_event.set()

    client = BitfinexWebSocketClient()
    with patch("api.websocket.bitfinex.websockets.connect", return_value=socket):
        await asyncio.wait_for(
            client.stream_prices(
                symbols={"BTCUSD"},
                on_price=on_price,
                on_status=on_status,
                stop_event=stop_event,
            ),
            timeout=1.0,
        )

    assert updates[0]["symbol"] == "BTCUSD"
    assert "connected" in statuses
    assert "disconnected" in statuses


@pytest.mark.asyncio
async def test_bitfinex_stream_prices_reports_disconnect_on_error() -> None:
    statuses: list[str] = []
    stop_event = asyncio.Event()

    async def on_status(status: str) -> None:
        statuses.append(status)
        if status == "disconnected":
            stop_event.set()

    async def on_price(update: dict[str, object]) -> None:
        pass

    client = BitfinexWebSocketClient()
    with (
        patch("api.websocket.bitfinex.websockets.connect", side_effect=RuntimeError("boom")),
        patch("api.websocket.bitfinex.asyncio.sleep", new=AsyncMock()),
    ):
        await asyncio.wait_for(
            client.stream_prices(
                symbols={"BTCUSD"},
                on_price=on_price,
                on_status=on_status,
                stop_event=stop_event,
            ),
            timeout=1.0,
        )

    assert "disconnected" in statuses
