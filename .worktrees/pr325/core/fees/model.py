from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.types import CostEstimate, FeeBreakdown

BPS_IN_PERCENT = Decimal(10_000)

# Default Bitfinex-like fee schedule for paper trading
DEFAULT_FEE_BREAKDOWN = FeeBreakdown(
    currency="USD",
    maker_fee_rate=Decimal("0.001"),  # 0.10% maker (limit)
    taker_fee_rate=Decimal("0.002"),  # 0.20% taker (market)
    assumed_spread_bps=10,  # 10 bps assumed spread
    assumed_slippage_bps=5,  # 5 bps assumed slippage
)


@dataclass(frozen=True)
class FeeModel:
    """Fee/cost model for paper and live trading.

    Models the full cost of a trade: taker/maker fees, assumed spread,
    and assumed slippage. Used by PaperExecutor to compute realistic P&L.

    Authoritative specs live in `docs/` (see `docs/ARCHITECTURE.md` and `docs/TODO.md`).
    """

    breakdown: FeeBreakdown = DEFAULT_FEE_BREAKDOWN

    def estimate_cost(self, *, gross_notional: Decimal, taker: bool = True) -> CostEstimate:
        """Estimate trading costs for a positive gross notional amount."""
        if gross_notional <= 0:
            raise ValueError("gross_notional must be positive")

        fee_rate = self.breakdown.taker_fee_rate if taker else self.breakdown.maker_fee_rate
        estimated_fees = (gross_notional * fee_rate).quantize(Decimal("0.00000001"))

        spread_cost = (gross_notional * Decimal(self.breakdown.assumed_spread_bps) / BPS_IN_PERCENT).quantize(
            Decimal("0.00000001")
        )
        slippage_cost = (gross_notional * Decimal(self.breakdown.assumed_slippage_bps) / BPS_IN_PERCENT).quantize(
            Decimal("0.00000001")
        )

        total = (estimated_fees + spread_cost + slippage_cost).quantize(Decimal("0.00000001"))
        minimum_edge_rate = (total / gross_notional).quantize(Decimal("0.00000001"))
        minimum_edge_bps = (minimum_edge_rate * BPS_IN_PERCENT).quantize(Decimal("0.01"))

        return CostEstimate(
            fee_currency=self.breakdown.currency,
            gross_notional=gross_notional,
            estimated_fees=estimated_fees,
            estimated_spread_cost=spread_cost,
            estimated_slippage_cost=slippage_cost,
            estimated_total_cost=total,
            minimum_edge_rate=minimum_edge_rate,
            minimum_edge_bps=minimum_edge_bps,
        )

    def minimum_edge_threshold_bps(
        self, *, gross_notional: Decimal, taker: bool = True, cost_estimate: CostEstimate | None = None
    ) -> Decimal:
        """Return the minimum edge, in basis points, needed to cover estimated costs."""
        estimate = cost_estimate or self.estimate_cost(gross_notional=gross_notional, taker=taker)
        return estimate.minimum_edge_bps
