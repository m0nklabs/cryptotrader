from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.types import CostEstimate, FeeBreakdown


@dataclass(frozen=True)
class FeeModel:
    """Fee/cost model.

    This is intentionally minimal scaffolding.

    Authoritative specs live in `docs/` (see `docs/ARCHITECTURE.md` and `docs/TODO.md`).
    """

    breakdown: FeeBreakdown

    def estimate_cost(self, *, gross_notional: Decimal, taker: bool = True) -> CostEstimate:
        fee_rate = self.breakdown.taker_fee_rate if taker else self.breakdown.maker_fee_rate
        estimated_fees = (gross_notional * fee_rate).quantize(Decimal("0.00000001"))

        spread_cost = (gross_notional * Decimal(self.breakdown.assumed_spread_bps) / Decimal(10_000)).quantize(
            Decimal("0.00000001")
        )
        slippage_cost = (gross_notional * Decimal(self.breakdown.assumed_slippage_bps) / Decimal(10_000)).quantize(
            Decimal("0.00000001")
        )

        total = (estimated_fees + spread_cost + slippage_cost).quantize(Decimal("0.00000001"))

        return CostEstimate(
            fee_currency=self.breakdown.currency,
            gross_notional=gross_notional,
            estimated_fees=estimated_fees,
            estimated_spread_cost=spread_cost,
            estimated_slippage_cost=slippage_cost,
            estimated_total_cost=total,
        )
