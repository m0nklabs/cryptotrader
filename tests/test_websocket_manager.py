from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.websocket.manager import PriceWebSocketManager


class DummyClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.last_symbols: set[str] | None = None
        self.stop_event: asyncio.Event | None = None

    async def stream_prices(
        self,
        *,
        symbols: set[str],
        on_price,
        on_status,
        stop_event: asyncio.Event,
    ) -> None:
        self.last_symbols = symbols
        self.stop_event = stop_event
        self.started.set()
        await stop_event.wait()


@pytest.mark.asyncio
async def test_manager_starts_stream_on_subscription() -> None:
    client = DummyClient()
    manager = PriceWebSocketManager(clients={"bitfinex": client}, rate_limit_seconds=0.0)

    websocket = AsyncMock()
    await manager.connect(websocket)
    await manager.update_subscription(websocket, exchange="bitfinex", symbols={"BTCUSD"})

    await asyncio.wait_for(client.started.wait(), timeout=1.0)
    assert client.last_symbols == {"BTCUSD"}

    await manager.disconnect(websocket)
    assert client.stop_event is not None
    assert client.stop_event.is_set() is True


@pytest.mark.asyncio
async def test_manager_broadcasts_to_subscribers_with_rate_limit() -> None:
    client = DummyClient()
    manager = PriceWebSocketManager(clients={"bitfinex": client}, rate_limit_seconds=10.0)

    websocket = AsyncMock()
    await manager.connect(websocket)
    await manager.update_subscription(websocket, exchange="bitfinex", symbols={"BTCUSD"})
    await asyncio.wait_for(client.started.wait(), timeout=1.0)

    update = {
        "type": "price",
        "exchange": "bitfinex",
        "symbol": "BTCUSD",
        "price": 50000.0,
        "timestamp": 1700000000000,
    }

    await manager.broadcast_price(update)
    await manager.broadcast_price(update)

    assert websocket.send_json.call_count == 1
