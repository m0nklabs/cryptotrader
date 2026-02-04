from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TypedDict
from unittest.mock import Mock

import pytest

from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient
from core.execution.bitfinex_live import BitfinexLiveAdapter, BitfinexLiveExecutor, create_bitfinex_live_executor
from core.execution.interfaces import Order
from core.types import OrderIntent


class SubmitOrderPayload(TypedDict):
    symbol: str
    amount: float
    price: float
    order_type: str


class DummyBitfinexClient(BitfinexClient):
    def __init__(self) -> None:
        super().__init__(api_key="key", api_secret="secret")
        self.last_payload: SubmitOrderPayload | None = None

    def submit_order(
        self,
        symbol: str,
        amount: float,
        price: float = None,
        order_type: str = "EXCHANGE LIMIT",
        flags: int = 0,
        cid: int | None = None,
    ) -> dict[str, object]:  # type: ignore[override]
        self.last_payload = SubmitOrderPayload(
            "symbol": symbol,
            "amount": amount,
            "price": price,
            "order_type": order_type,
        )
        return {"status": "success", "order_id": 1234, "data": []}


def test_create_bitfinex_live_executor_requires_credentials() -> None:
    with pytest.raises(ValueError):
        create_bitfinex_live_executor(dry_run=False, api_key="", api_secret="")


def test_create_bitfinex_live_executor_dry_run_allows_missing_credentials() -> None:
    executor = create_bitfinex_live_executor(dry_run=True, api_key="", api_secret="")
    assert isinstance(executor, BitfinexLiveExecutor)


def test_adapter_raises_on_limit_without_price() -> None:
    adapter = BitfinexLiveAdapter(client=DummyBitfinexClient())
    with pytest.raises(ValueError, match="limit orders require price"):
        adapter.create_order(
            symbol="BTCUSD",
            side="BUY",
            amount=Decimal("1"),
            order_type="limit",
            price=None,
            dry_run=False,
        )


def test_adapter_raises_when_order_id_missing() -> None:
    client = DummyBitfinexClient()
    client.submit_order = Mock(return_value={"status": "success", "order_id": None, "data": []})  # type: ignore[assignment]
    adapter = BitfinexLiveAdapter(client=client)

    with pytest.raises(RuntimeError, match="order_id"):
        adapter.create_order(symbol="BTCUSD", side="BUY", amount=Decimal("1"), dry_run=False)


def test_adapter_converts_signed_amounts() -> None:
    client = DummyBitfinexClient()
    adapter = BitfinexLiveAdapter(client=client)

    adapter.create_order(symbol="BTCUSD", side="SELL", amount=Decimal("2"), dry_run=False)
    assert client.last_payload is not None
    assert client.last_payload["amount"] == -2.0


def test_executor_handles_adapter_error() -> None:
    adapter = Mock(spec=BitfinexLiveAdapter)
    adapter.create_order.side_effect = RuntimeError("boom")
    executor = BitfinexLiveExecutor(adapter=adapter, dry_run=False)
    intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="BUY", amount=Decimal("1"))

    result = executor.execute(intent)
    assert result.accepted is False
    assert "execution error" in result.reason


def test_executor_dry_run_passes_through() -> None:
    fixed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    adapter = Mock(spec=BitfinexLiveAdapter)
    adapter.create_order.return_value = Order(
        id="dry-run",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("1"),
        price=None,
        status="dry_run",
        timestamp=fixed_time,
    )
    executor = BitfinexLiveExecutor(adapter=adapter, dry_run=True)
    intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="BUY", amount=Decimal("1"))

    result = executor.execute(intent)
    adapter.create_order.assert_called_once()
    called_kwargs = adapter.create_order.call_args.kwargs
    assert called_kwargs["dry_run"] is True
    assert result.dry_run is True
