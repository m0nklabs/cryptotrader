from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskLimits:
    """Risk limits configuration.

    Pure data model (no execution side effects).
    """

    max_order_notional: Decimal | None = None
    max_daily_trades: int | None = None
    cooldown_seconds: int | None = None
