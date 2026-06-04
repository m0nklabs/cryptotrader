from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fees.model import FeeModel
from core.types import FeeBreakdown


def _default_fee_model() -> FeeModel:
    return FeeModel(
        FeeBreakdown(
            currency="USD",
            maker_fee_rate=Decimal("0.001"),
            taker_fee_rate=Decimal("0.002"),
            assumed_spread_bps=10,
            assumed_slippage_bps=5,
        )
    )


def test_estimate_cost_computes_fees_and_edge_threshold() -> None:
    model = _default_fee_model()
    estimate = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)

    assert estimate.estimated_fees == Decimal("2.00000000")
    assert estimate.estimated_spread_cost == Decimal("1.00000000")
    assert estimate.estimated_slippage_cost == Decimal("0.50000000")
    assert estimate.estimated_total_cost == Decimal("3.50000000")
    assert estimate.minimum_edge_rate == Decimal("0.00350000")
    assert estimate.minimum_edge_bps == Decimal("35.00")


def test_minimum_edge_threshold_helper_uses_maker_rate() -> None:
    model = _default_fee_model()

    assert model.minimum_edge_threshold_bps(gross_notional=Decimal("1000"), taker=False) == Decimal("25.00")
