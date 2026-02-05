from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient
from core.execution.interfaces import ExchangeAdapter, Order
from core.types import ExecutionResult, OrderIntent


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BitfinexLiveAdapter:
    """Live Bitfinex adapter that supports dry-run.

    The adapter always receives the executor's dry_run flag when called via
    BitfinexLiveExecutor.execute(), even if credentials are configured.
    This adapter submits EXCHANGE (spot) orders only; margin trading is out of scope.
    """

    client: BitfinexClient

    def create_order(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        amount: Decimal,
        price: Decimal | None = None,
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

        # submit_order handles symbol normalization (adds 't' prefix if missing).
        result = self.client.submit_order(
            symbol=symbol,
            amount=str(signed_amount),
            price=str(price) if price is not None else "0",
            order_type="EXCHANGE MARKET" if order_type == "market" else "EXCHANGE LIMIT",
        )
        order_id = result.get("order_id")
        if order_id is None:
            raise RuntimeError(
                "Bitfinex order submission failed: expected non-null order_id for "
                f"live order but got none. Response: {result!r}"
            )

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
    """Order executor for Bitfinex live trading with dry-run support.

    The executor always passes its dry_run flag to the adapter, so adapter
    credential configuration is independent from execution mode.
    """

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
            mode = "dry_run" if self.dry_run else "live"
            return ExecutionResult(
                dry_run=self.dry_run,
                accepted=False,
                reason=f"{mode} execution error: {exc}",
                order_id=None,
                raw={"error": str(exc), "mode": mode},
            )


def _build_private_client(*, api_key: str | None = None, api_secret: str | None = None) -> BitfinexClient:
    return BitfinexClient(api_key=api_key, api_secret=api_secret)


def _has_valid_credentials(client: BitfinexClient) -> bool:
    return bool(client.api_key and client.api_secret and client.api_key.strip() and client.api_secret.strip())


def create_bitfinex_live_executor(
    *,
    dry_run: bool = True,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> BitfinexLiveExecutor:
    """Convenience factory for :class:`BitfinexLiveExecutor`.

    Builds a private :class:`BitfinexClient`, wraps it in a
    :class:`BitfinexLiveAdapter`, and returns a :class:`BitfinexLiveExecutor`
    configured for dry-run (paper trading) or live trading.

    Args:
        dry_run: When True (default), the executor runs in paper-trading mode.
        api_key: Optional Bitfinex API key (falls back to environment if omitted).
        api_secret: Optional Bitfinex API secret (falls back to environment if omitted).

    Returns:
        BitfinexLiveExecutor configured for the requested execution mode.

    Raises:
        ValueError: If dry_run is False and no valid API credentials are available.
    """

    client = _build_private_client(api_key=api_key, api_secret=api_secret)
    if not dry_run and not _has_valid_credentials(client):
        raise ValueError(
            "Bitfinex live trading requires API credentials. Provide api_key/api_secret or set "
            "BITFINEX_API_KEY/BITFINEX_API_SECRET in the environment."
        )
    adapter = BitfinexLiveAdapter(client=client)
    return BitfinexLiveExecutor(adapter=adapter, dry_run=dry_run)
