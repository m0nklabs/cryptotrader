from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
import contextlib
from typing import Awaitable, Callable, Protocol

from api.websocket.binance import BinanceWebSocketClient
from api.websocket.bitfinex import BitfinexWebSocketClient

logger = logging.getLogger(__name__)


class WebSocketLike(Protocol):
    async def send_json(self, data: object) -> None: ...


PriceCallback = Callable[[dict[str, object]], Awaitable[None]]
StatusCallback = Callable[[str], Awaitable[None]]


class ExchangePriceClient(Protocol):
    async def stream_prices(
        self,
        *,
        symbols: set[str],
        on_price: PriceCallback,
        on_status: StatusCallback,
        stop_event: asyncio.Event,
    ) -> None: ...


@dataclass
class ConnectionState:
    exchange: str
    symbols: set[str] = field(default_factory=set)
    last_sent: dict[str, float] = field(default_factory=dict)


@dataclass
class ExchangeState:
    symbols: set[str] = field(default_factory=set)
    task: asyncio.Task | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)


class PriceWebSocketManager:
    """Manage WebSocket subscribers and exchange streaming tasks."""

    def __init__(
        self,
        *,
        clients: dict[str, ExchangePriceClient] | None = None,
        rate_limit_seconds: float = 0.5,
    ) -> None:
        self._clients = clients or {
            "binance": BinanceWebSocketClient(),
            "bitfinex": BitfinexWebSocketClient(),
        }
        self._rate_limit_seconds = rate_limit_seconds
        self._connections: dict[WebSocketLike, ConnectionState] = {}
        self._exchange_state: dict[str, ExchangeState] = {}
        self._lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocketLike, *, exchange: str = "bitfinex") -> None:
        async with self._lock:
            self._connections[websocket] = ConnectionState(exchange=exchange)

    async def disconnect(self, websocket: WebSocketLike) -> None:
        async with self._lock:
            state = self._connections.pop(websocket, None)
        if state:
            async with self._refresh_lock:
                await self._refresh_exchange_stream(state.exchange)

    async def update_subscription(self, websocket: WebSocketLike, *, exchange: str, symbols: set[str]) -> None:
        async with self._lock:
            prev_exchange = self._connections.get(websocket, ConnectionState(exchange=exchange)).exchange
            self._connections[websocket] = ConnectionState(exchange=exchange, symbols=set(symbols))

        async with self._refresh_lock:
            await self._refresh_exchange_stream(prev_exchange)
            await self._refresh_exchange_stream(exchange)

    async def broadcast_price(self, update: dict[str, object]) -> None:
        exchange = str(update.get("exchange", ""))
        symbol = str(update.get("symbol", ""))
        if not exchange or not symbol:
            return

        now = time.monotonic()
        async with self._lock:
            connections = list(self._connections.items())

        failures: list[WebSocketLike] = []
        for websocket, state in connections:
            if state.exchange != exchange or symbol not in state.symbols:
                continue
            last_sent = state.last_sent.get(symbol, 0.0)
            if now - last_sent < self._rate_limit_seconds:
                continue
            state.last_sent[symbol] = now
            try:
                await websocket.send_json(update)
            except Exception:
                logger.warning("Failed to send price update to websocket", exc_info=True)
                failures.append(websocket)

        for websocket in failures:
            await self.disconnect(websocket)

    async def broadcast_status(self, *, exchange: str, status: str) -> None:
        payload = {"type": "status", "exchange": exchange, "status": status}
        async with self._lock:
            connections = list(self._connections.items())

        failures: list[WebSocketLike] = []
        for websocket, state in connections:
            if state.exchange != exchange:
                continue
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.warning("Failed to send status update to websocket", exc_info=True)
                failures.append(websocket)

        for websocket in failures:
            await self.disconnect(websocket)

    async def _refresh_exchange_stream(self, exchange: str) -> None:
        task_to_stop: asyncio.Task | None = None
        stop_event: asyncio.Event | None = None
        client: ExchangePriceClient | None = None
        expected_stop_event: asyncio.Event | None = None
        async with self._lock:
            symbols = set()
            for state in self._connections.values():
                if state.exchange == exchange:
                    symbols.update(state.symbols)

            state = self._exchange_state.get(exchange)
            if state is None:
                state = ExchangeState()
                self._exchange_state[exchange] = state

            if symbols == state.symbols:
                return

            if state.task:
                state.stop_event.set()
                task_to_stop = state.task
                stop_event = state.stop_event
                state.task = None

            if not symbols:
                state.symbols = set()
                state.stop_event = asyncio.Event()
                return

            state.symbols = set(symbols)
            state.stop_event = asyncio.Event()
            expected_stop_event = state.stop_event
            client = self._clients.get(exchange)

        if task_to_stop and stop_event:
            await self._await_task(task_to_stop, stop_event)

        if client is None:
            logger.warning("No WebSocket client registered for exchange '%s'", exchange)
            return

        async def _runner() -> None:
            await client.stream_prices(
                symbols=symbols,
                on_price=self.broadcast_price,
                on_status=lambda status: self.broadcast_status(exchange=exchange, status=status),
                stop_event=state.stop_event,
            )

        async with self._lock:
            current_state = self._exchange_state.get(exchange)
            if current_state is None or current_state.stop_event is not expected_stop_event:
                return
            current_state.task = asyncio.create_task(_runner())

    async def _await_task(self, task: asyncio.Task, stop_event: asyncio.Event) -> None:
        stop_event.set()
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        except asyncio.CancelledError:
            return


_price_ws_manager: PriceWebSocketManager | None = None


def get_price_ws_manager() -> PriceWebSocketManager:
    global _price_ws_manager
    if _price_ws_manager is None:
        _price_ws_manager = PriceWebSocketManager()
    return _price_ws_manager
