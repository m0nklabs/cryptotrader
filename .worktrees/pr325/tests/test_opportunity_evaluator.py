"""Unit tests for opportunity evaluator.

Tests cover:
- Pass case: edge exceeds required threshold
- Fail case: edge below required threshold
- Boundary case: edge exactly equals threshold
- Edge cases: validation errors, zero edge, etc.
"""

from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fees.model import FeeModel
from core.opportunities.evaluator import evaluate_opportunity
from core.types import FeeBreakdown
import pytest


def _default_fee_model() -> FeeModel:
    """Create a standard fee model for testing."""
    return FeeModel(
        FeeBreakdown(
            currency="USD",
            maker_fee_rate=Decimal("0.001"),  # 0.1% = 10 bps
            taker_fee_rate=Decimal("0.002"),  # 0.2% = 20 bps
            assumed_spread_bps=10,
            assumed_slippage_bps=5,
        )
    )


def test_evaluate_opportunity_pass_case() -> None:
    """Test PASS decision when edge exceeds required threshold."""
    fee_model = _default_fee_model()

    # For $1000 notional with taker fee:
    # - Fees: $1000 * 0.002 = $2.00 (20 bps)
    # - Spread: $1000 * 0.001 = $1.00 (10 bps)
    # - Slippage: $1000 * 0.0005 = $0.50 (5 bps)
    # - Total: $3.50 (35 bps required)

    # Test with 50 bps edge (should pass)
    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.005"),  # 50 bps
        fee_model=fee_model,
        taker=True,
    )

    assert result.decision == "PASS"
    assert result.required_bps == Decimal("35.00")
    assert result.observed_bps == Decimal("50.00")
    assert len(result.reasons) == 2
    assert "50.00 bps >= required 35.00 bps" in result.reasons[0]
    assert "surplus: 15.00 bps" in result.reasons[0]
    assert "Estimated costs" in result.reasons[1]
    assert result.cost_estimate is not None
    assert result.cost_estimate.estimated_total_cost == Decimal("3.50000000")


def test_evaluate_opportunity_fail_case() -> None:
    """Test FAIL decision when edge is below required threshold."""
    fee_model = _default_fee_model()

    # Test with 12 bps edge (should fail, need 35 bps)
    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.0012"),  # 12 bps
        fee_model=fee_model,
        taker=True,
    )

    assert result.decision == "FAIL"
    assert result.required_bps == Decimal("35.00")
    assert result.observed_bps == Decimal("12.00")
    assert len(result.reasons) == 2
    assert "12.00 bps < required 35.00 bps" in result.reasons[0]
    assert "deficit: 23.00 bps" in result.reasons[0]
    assert "Estimated costs" in result.reasons[1]
    assert result.cost_estimate is not None


def test_evaluate_opportunity_boundary_equal_threshold() -> None:
    """Test boundary case when edge exactly equals required threshold."""
    fee_model = _default_fee_model()

    # Test with exactly 35 bps edge (boundary: should pass)
    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.0035"),  # 35 bps
        fee_model=fee_model,
        taker=True,
    )

    assert result.decision == "PASS"
    assert result.required_bps == Decimal("35.00")
    assert result.observed_bps == Decimal("35.00")
    assert "35.00 bps >= required 35.00 bps" in result.reasons[0]
    assert "surplus: 0.00 bps" in result.reasons[0]


def test_evaluate_opportunity_maker_fees_lower_threshold() -> None:
    """Test that maker fees result in lower required threshold than taker fees."""
    fee_model = _default_fee_model()

    # Maker fees: 10 bps (vs taker 20 bps)
    # Total required: 10 (fee) + 10 (spread) + 5 (slippage) = 25 bps
    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.003"),  # 30 bps
        fee_model=fee_model,
        taker=False,  # Use maker fees
    )

    assert result.decision == "PASS"
    assert result.required_bps == Decimal("25.00")  # Lower than taker's 35 bps
    assert result.observed_bps == Decimal("30.00")


def test_evaluate_opportunity_zero_edge_fails() -> None:
    """Test that zero edge always fails."""
    fee_model = _default_fee_model()

    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0"),  # 0 bps
        fee_model=fee_model,
        taker=True,
    )

    assert result.decision == "FAIL"
    assert result.observed_bps == Decimal("0.00")
    assert result.required_bps == Decimal("35.00")


def test_evaluate_opportunity_with_precomputed_cost_estimate() -> None:
    """Test evaluation with pre-computed cost estimate."""
    fee_model = _default_fee_model()

    # Pre-compute cost estimate
    cost_estimate = fee_model.estimate_cost(
        gross_notional=Decimal("1000"),
        taker=True,
    )

    # Evaluate with pre-computed estimate
    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.005"),  # 50 bps
        fee_model=fee_model,
        taker=True,
        cost_estimate=cost_estimate,
    )

    assert result.decision == "PASS"
    assert result.cost_estimate is cost_estimate  # Same instance


def test_evaluate_opportunity_different_notional_scales_threshold() -> None:
    """Test that required threshold scales correctly with notional size."""
    fee_model = _default_fee_model()

    # Small notional: $100
    result_small = evaluate_opportunity(
        gross_notional=Decimal("100"),
        edge_rate=Decimal("0.005"),  # 50 bps
        fee_model=fee_model,
        taker=True,
    )

    # Large notional: $10,000
    result_large = evaluate_opportunity(
        gross_notional=Decimal("10000"),
        edge_rate=Decimal("0.005"),  # 50 bps
        fee_model=fee_model,
        taker=True,
    )

    # Required bps should be the same (percentage-based)
    assert result_small.required_bps == result_large.required_bps == Decimal("35.00")
    assert result_small.decision == result_large.decision == "PASS"


def test_evaluate_opportunity_validates_positive_notional() -> None:
    """Test validation: gross_notional must be positive."""
    fee_model = _default_fee_model()

    with pytest.raises(ValueError, match="gross_notional must be positive"):
        evaluate_opportunity(
            gross_notional=Decimal("0"),
            edge_rate=Decimal("0.005"),
            fee_model=fee_model,
            taker=True,
        )

    with pytest.raises(ValueError, match="gross_notional must be positive"):
        evaluate_opportunity(
            gross_notional=Decimal("-100"),
            edge_rate=Decimal("0.005"),
            fee_model=fee_model,
            taker=True,
        )


def test_evaluate_opportunity_validates_non_negative_edge() -> None:
    """Test validation: edge_rate must be non-negative."""
    fee_model = _default_fee_model()

    with pytest.raises(ValueError, match="edge_rate must be non-negative"):
        evaluate_opportunity(
            gross_notional=Decimal("1000"),
            edge_rate=Decimal("-0.005"),  # Negative edge
            fee_model=fee_model,
            taker=True,
        )


def test_evaluate_opportunity_very_high_edge_passes() -> None:
    """Test that very high edge (100+ bps) passes easily."""
    fee_model = _default_fee_model()

    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.02"),  # 200 bps
        fee_model=fee_model,
        taker=True,
    )

    assert result.decision == "PASS"
    assert result.observed_bps == Decimal("200.00")
    assert result.required_bps == Decimal("35.00")
    assert "surplus: 165.00 bps" in result.reasons[0]


def test_evaluate_opportunity_result_immutable() -> None:
    """Test that EvaluationResult is immutable (frozen dataclass)."""
    fee_model = _default_fee_model()

    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.005"),
        fee_model=fee_model,
        taker=True,
    )

    # Attempt to modify should raise error
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        result.decision = "FAIL"  # type: ignore


def test_evaluate_opportunity_reasons_contain_cost_breakdown() -> None:
    """Test that reasons include detailed cost breakdown."""
    fee_model = _default_fee_model()

    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.005"),
        fee_model=fee_model,
        taker=True,
    )

    # Second reason should contain cost breakdown
    cost_reason = result.reasons[1]
    assert "fees=" in cost_reason
    assert "spread=" in cost_reason
    assert "slippage=" in cost_reason
    assert "total=" in cost_reason
    assert "USD" in cost_reason


def test_evaluate_opportunity_close_to_boundary() -> None:
    """Test cases very close to the boundary threshold."""
    fee_model = _default_fee_model()

    # Just barely passes (35.01 bps)
    result_pass = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.003501"),  # 35.01 bps
        fee_model=fee_model,
        taker=True,
    )
    assert result_pass.decision == "PASS"

    # Just barely fails (34.99 bps)
    result_fail = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.003499"),  # 34.99 bps
        fee_model=fee_model,
        taker=True,
    )
    assert result_fail.decision == "FAIL"
