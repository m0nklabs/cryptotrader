from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional

from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient
from core.execution.interfaces import ExchangeAdapter, Order
from core.types import ExecutionResult, OrderIntent


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BitfinexLiveAdapter(ExchangeAdapter):
    """Live Bitfinex adapter that supports dry-run."""

    client: BitfinexClient

    def create_order(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        amount: Decimal,
        price: Optional[Decimal] = None,
        order_type: Literal["market", "limit"] = "market",
        dry_run: bool = True,
    ) -> Order:
        signed_amount = amount if side == "BUY" else -amount

        if dry_run:
            return Order(
                id="dry-run",
                symbol=symbol,
                side=side,
                amount=amount,
                price=price,
                status="dry_run",
                timestamp=Order.now_timestamp(),
            )

        if order_type == "limit" and price is None:
            raise ValueError("limit orders require price")

        result = self.client.submit_order(
            symbol=f"t{symbol}",
            amount=float(signed_amount),
            price=float(price) if price is not None else 0.0,
            order_type="EXCHANGE MARKET" if order_type == "market" else "EXCHANGE LIMIT",
        )
        order_id = result.get("order_id")
        if order_id is None:
            raise RuntimeError("Bitfinex order submission failed")

        return Order(
            id=str(order_id),
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            status="submitted",
            timestamp=Order.now_timestamp(),
        )


@dataclass(frozen=True)
class BitfinexLiveExecutor:
    """Order executor for Bitfinex live trading with dry-run support."""

    adapter: ExchangeAdapter
    dry_run: bool = True

    def execute(self, order: OrderIntent) -> ExecutionResult:
        try:
            created = self.adapter.create_order(
                symbol=order.symbol,
                side=order.side,
                amount=order.amount,
                price=order.limit_price,
                order_type=order.order_type,
                dry_run=self.dry_run,
            )
            return ExecutionResult(
                dry_run=self.dry_run,
                accepted=True,
                reason="submitted" if not self.dry_run else "dry-run",
                order_id=created.id,
                raw={
                    "symbol": created.symbol,
                    "side": created.side,
                    "amount": str(created.amount),
                    "price": str(created.price) if created.price is not None else None,
                    "status": created.status,
                    "timestamp": created.timestamp.isoformat(),
                },
            )
        except Exception as exc:
            logger.exception("Bitfinex order execution failed")
            return ExecutionResult(
                dry_run=self.dry_run,
                accepted=False,
                reason=str(exc),
                order_id=None,
                raw={"error": str(exc)},
            )


def _build_private_client(*, api_key: Optional[str] = None, api_secret: Optional[str] = None) -> BitfinexClient:
    return BitfinexClient(api_key=api_key, api_secret=api_secret)


def create_bitfinex_live_executor(*, dry_run: bool = True) -> BitfinexLiveExecutor:
    """Convenience factory for Bitfinex live executor."""

    client = _build_private_client()
    adapter = BitfinexLiveAdapter(client=client)
    return BitfinexLiveExecutor(adapter=adapter, dry_run=dry_run)
