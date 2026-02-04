from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional, Protocol

from core.types import ExecutionResult, OrderIntent


@dataclass(frozen=True)
class Order:
    id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    amount: Decimal
    price: Optional[Decimal]
    status: str
    timestamp: datetime

    @staticmethod
    def now_timestamp() -> datetime:
        return datetime.now(timezone.utc)


class ExchangeAdapter(Protocol):
    """Unified interface for live exchange adapters."""

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
        """Create an order on the exchange. Defaults to dry-run."""


class OrderExecutor(Protocol):
    """Protocol for order execution (paper or live)."""

    def execute(self, order: OrderIntent) -> ExecutionResult:
        """Execute an order and return the result."""
