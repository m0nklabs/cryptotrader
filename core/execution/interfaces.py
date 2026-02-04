from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional, Protocol

from core.types import ExecutionResult, OrderIntent


@dataclass(frozen=True)
class Order:
    """Normalized order record (price is None for market orders).

    Timestamps are expected to be timezone-aware (UTC).
    """

    id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    amount: Decimal
    price: Optional[Decimal]
    status: str
    timestamp: datetime

    @staticmethod
    def now_timestamp() -> datetime:
        """Return a timezone-aware timestamp in UTC."""
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
        """Create an order on the exchange. Defaults to dry-run.

        Implementations may use blocking I/O; callers should offload to a thread
        executor when used from async contexts.
        """


class OrderExecutor(Protocol):
    """Protocol for order execution (paper or live)."""

    def execute(self, order: OrderIntent) -> ExecutionResult:
        """Execute an order and return the result.

        Implementations may perform blocking work; prefer running in a thread
        executor when integrating with async code.
        """
