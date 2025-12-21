from __future__ import annotations

from dataclasses import dataclass

from core.types import ExecutionResult, OrderIntent


@dataclass(frozen=True)
class PaperExecutor:
    """Dry-run executor.

    This never places real orders. It returns what *would* have been executed.
    """

    def execute(self, order: OrderIntent) -> ExecutionResult:
        return ExecutionResult(
            dry_run=True,
            accepted=True,
            reason="paper-execution",
            order_id=None,
            raw={
                "exchange": order.exchange,
                "symbol": order.symbol,
                "side": order.side,
                "amount": str(order.amount),
                "order_type": order.order_type,
                "limit_price": str(order.limit_price) if order.limit_price is not None else None,
            },
        )
