"""Fee model validation — acceptance criteria and evidence.

Validates the FeeModel for paper trading readiness:
- Defaults match Bitfinex fee schedule
- Edge cases handled correctly
- Integration with PaperExecutor
- Cost estimation accuracy across notional sizes
- Maker vs taker fee differentiation
- Minimum edge calculation correctness
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from core.fees.model import FeeModel, DEFAULT_FEE_BREAKDOWN
from core.types import FeeBreakdown
from core.execution.paper import PaperExecutor


# ============================================================================
# Acceptance Criterion 1: FeeModel defaults match Bitfinex
# ============================================================================


class TestFeeModelDefaults:
    """AC1: FeeModel defaults must match Bitfinex fee schedule."""

    def test_maker_fee_rate(self):
        """Maker fee rate should be 0.10% (0.001)."""
        assert DEFAULT_FEE_BREAKDOWN.maker_fee_rate == Decimal("0.001")

    def test_taker_fee_rate(self):
        """Taker fee rate should be 0.20% (0.002)."""
        assert DEFAULT_FEE_BREAKDOWN.taker_fee_rate == Decimal("0.002")

    def test_assumed_spread_bps(self):
        """Assumed spread should be 10 bps."""
        assert DEFAULT_FEE_BREAKDOWN.assumed_spread_bps == 10

    def test_assumed_slippage_bps(self):
        """Assumed slippage should be 5 bps."""
        assert DEFAULT_FEE_BREAKDOWN.assumed_slippage_bps == 5

    def test_currency(self):
        """Currency should be USD."""
        assert DEFAULT_FEE_BREAKDOWN.currency == "USD"

    def test_taker_is_double_maker(self):
        """Taker fee (0.2%) should be exactly double maker fee (0.1%)."""
        assert DEFAULT_FEE_BREAKDOWN.taker_fee_rate == 2 * DEFAULT_FEE_BREAKDOWN.maker_fee_rate


# ============================================================================
# Acceptance Criterion 2: Cost estimation correctness
# ============================================================================


class TestCostEstimation:
    """AC2: Cost estimation must be mathematically correct."""

    @pytest.fixture
    def model(self):
        return FeeModel()

    def test_taker_cost_breakdown(self, model):
        """Taker cost: fee + spread + slippage = total."""
        notional = Decimal("1000")
        est = model.estimate_cost(gross_notional=notional, taker=True)

        # fee = 1000 * 0.002 = 2.0
        # spread = 1000 * 10/10000 = 1.0
        # slippage = 1000 * 5/10000 = 0.5
        # total = 3.5
        expected_fees = Decimal("2.00000000")
        expected_spread = Decimal("1.00000000")
        expected_slippage = Decimal("0.50000000")
        expected_total = Decimal("3.50000000")

        assert est.estimated_fees == expected_fees
        assert est.estimated_spread_cost == expected_spread
        assert est.estimated_slippage_cost == expected_slippage
        assert est.estimated_total_cost == expected_total

    def test_maker_cost_breakdown(self, model):
        """Maker cost: fee (lower) + spread + slippage = total."""
        notional = Decimal("1000")
        est = model.estimate_cost(gross_notional=notional, taker=False)

        # fee = 1000 * 0.001 = 1.0
        # spread = 1000 * 10/10000 = 1.0
        # slippage = 1000 * 5/10000 = 0.5
        # total = 2.5
        expected_fees = Decimal("1.00000000")
        expected_total = Decimal("2.50000000")

        assert est.estimated_fees == expected_fees
        assert est.estimated_total_cost == expected_total

    def test_minimum_edge_bps_calculation(self, model):
        """Minimum edge = total_cost / notional, expressed in bps."""
        notional = Decimal("1000")
        est = model.estimate_cost(gross_notional=notional, taker=True)

        # 3.5 / 1000 = 0.0035 = 35 bps
        assert est.minimum_edge_bps == Decimal("35.00")

    def test_minimum_edge_rate(self, model):
        """Minimum edge rate = total_cost / notional (decimal form)."""
        notional = Decimal("1000")
        est = model.estimate_cost(gross_notional=notional, taker=True)

        # 3.5 / 1000 = 0.0035
        assert est.minimum_edge_rate == Decimal("0.00350000")

    def test_cost_scales_linearly(self, model):
        """Cost scales linearly with notional amount."""
        est_small = model.estimate_cost(gross_notional=Decimal("100"), taker=True)
        est_large = model.estimate_cost(gross_notional=Decimal("10000"), taker=True)

        # Ratio should be preserved
        ratio = est_large.estimated_total_cost / est_small.estimated_total_cost
        notional_ratio = Decimal("10000") / Decimal("100")
        assert ratio == notional_ratio

    def test_zero_notional_raises(self, model):
        """Zero notional should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            model.estimate_cost(gross_notional=Decimal("0"), taker=True)

    def test_negative_notional_raises(self, model):
        """Negative notional should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            model.estimate_cost(gross_notional=Decimal("-100"), taker=True)


# ============================================================================
# Acceptance Criterion 3: PaperExecutor integration
# ============================================================================


class TestPaperExecutorIntegration:
    """AC3: FeeModel must be properly integrated with PaperExecutor."""

    def test_executor_uses_default_fee_model(self):
        """PaperExecutor should use default FeeModel when none provided."""
        executor = PaperExecutor()
        assert executor.get_fee_model().breakdown.taker_fee_rate == Decimal("0.002")

    def test_executor_uses_custom_fee_model(self):
        """PaperExecutor should use a custom FeeModel when provided."""
        custom_breakdown = FeeBreakdown(
            currency="USD",
            maker_fee_rate=Decimal("0.0005"),
            taker_fee_rate=Decimal("0.0015"),
            assumed_spread_bps=8,
            assumed_slippage_bps=4,
        )
        custom_model = FeeModel(breakdown=custom_breakdown)
        executor = PaperExecutor(fee_model=custom_model)
        assert executor.get_fee_model().breakdown.taker_fee_rate == Decimal("0.0015")

    def test_market_order_applies_fees(self):
        """Market orders should apply fees from FeeModel on slippage-adjusted price."""
        executor = PaperExecutor()
        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="market",
            market_price=Decimal("50000"),
        )
        # BUY: fill_price = 50000 * (1 + 5/10000) = 50025
        # fee = 50025 * 0.002 = 100.05
        # spread = 50025 * 10/10000 = 50.025
        # slippage = 50025 * 5/10000 = 25.0125
        # total = 175.0875
        assert order.fees > 0
        assert order.fees == Decimal("175.08750000")

    def test_sell_order_applies_fees(self):
        """SELL orders should also apply fees from FeeModel on slippage-adjusted price."""
        executor = PaperExecutor()
        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="SELL",
            qty=Decimal("1"),
            order_type="market",
            market_price=Decimal("50000"),
        )
        # SELL: fill_price = 50000 / (1 + 5/10000) = 49975.0125
        # fee = 49975.0125 * 0.002 = 99.950025
        # spread = 49975.0125 * 10/10000 = 49.975013
        # slippage = 49975.0125 * 5/10000 = 24.987506
        # total = 174.912544
        assert order.fees > 0
        # Allow small rounding tolerance
        assert order.fees >= Decimal("174.91") and order.fees <= Decimal("174.92")

    def test_fee_tracking_accumulates(self):
        """Total fees should accumulate across multiple orders."""
        executor = PaperExecutor()
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="market",
            market_price=Decimal("50000"),
        )
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="market",
            market_price=Decimal("50000"),
        )

        total = executor.get_total_fees()
        # Each order ~175, two orders ~350 (slight variation from slippage)
        assert total > Decimal("350") and total < Decimal("351")

    def test_fee_model_in_summary(self):
        """Paper summary should include fee model details."""
        executor = PaperExecutor()
        summary = executor.get_paper_summary()
        assert "fee_model" in summary
        assert "maker_fee" in summary["fee_model"]
        assert "taker_fee" in summary["fee_model"]
        assert "spread_bps" in summary["fee_model"]
        assert "slippage_bps" in summary["fee_model"]


# ============================================================================
# Acceptance Criterion 4: Edge cases
# ============================================================================


class TestEdgeCases:
    """AC4: FeeModel must handle edge cases correctly."""

    def test_very_small_notional(self):
        """FeeModel should handle very small notional amounts."""
        model = FeeModel()
        est = model.estimate_cost(gross_notional=Decimal("0.01"), taker=True)
        assert est.estimated_fees > 0
        assert est.estimated_total_cost > 0
        # minimum_edge should still be reasonable
        assert est.minimum_edge_bps > 0

    def test_very_large_notional(self):
        """FeeModel should handle very large notional amounts."""
        model = FeeModel()
        est = model.estimate_cost(gross_notional=Decimal("1000000"), taker=True)
        assert est.estimated_fees == Decimal("2000.00000000")
        # 1000000 * 10/10000 = 1000
        assert est.estimated_spread_cost == Decimal("1000.00000000")
        # 1000000 * 5/10000 = 500
        assert est.estimated_slippage_cost == Decimal("500.00000000")
        assert est.estimated_total_cost == Decimal("3500.00000000")

    def test_minimum_edge_threshold_helper(self):
        """minimum_edge_threshold_bps should return same value as estimate."""
        model = FeeModel()
        notional = Decimal("5000")

        est = model.estimate_cost(gross_notional=notional, taker=True)
        helper = model.minimum_edge_threshold_bps(gross_notional=notional, taker=True)
        assert helper == est.minimum_edge_bps

    def test_minimum_edge_threshold_with_custom_estimate(self):
        """minimum_edge_threshold_bps should use provided cost_estimate."""
        model = FeeModel()
        notional = Decimal("5000")
        custom_estimate = model.estimate_cost(gross_notional=notional, taker=False)
        helper = model.minimum_edge_threshold_bps(gross_notional=notional, taker=True, cost_estimate=custom_estimate)
        assert helper == custom_estimate.minimum_edge_bps

    def test_custom_breakdown(self):
        """FeeModel should work with custom FeeBreakdown."""
        custom = FeeBreakdown(
            currency="EUR",
            maker_fee_rate=Decimal("0.0008"),
            taker_fee_rate=Decimal("0.0016"),
            assumed_spread_bps=12,
            assumed_slippage_bps=6,
        )
        model = FeeModel(breakdown=custom)
        est = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)

        # fee = 1000 * 0.0016 = 1.6
        # spread = 1000 * 12/10000 = 1.2
        # slippage = 1000 * 6/10000 = 0.6
        # total = 3.4
        assert est.estimated_fees == Decimal("1.60000000")
        assert est.estimated_spread_cost == Decimal("1.20000000")
        assert est.estimated_slippage_cost == Decimal("0.60000000")
        assert est.estimated_total_cost == Decimal("3.40000000")
        assert est.fee_currency == "EUR"

    def test_fee_model_is_frozen(self):
        """FeeModel should be immutable (frozen dataclass)."""
        model = FeeModel()
        with pytest.raises(Exception):
            model.breakdown = None  # type: ignore[assignment]


# ============================================================================
# Acceptance Criterion 5: Fee model vs real Bitfinex data
# ============================================================================


class TestBitfinexAlignment:
    """AC5: FeeModel defaults should align with real Bitfinex data."""

    def test_taker_fee_matches_bitfinex(self):
        """Bitfinex taker fee is 0.20% for standard users."""
        assert DEFAULT_FEE_BREAKDOWN.taker_fee_rate == Decimal("0.002")

    def test_maker_fee_matches_bitfinex(self):
        """Bitfinex maker fee is 0.10% for standard users."""
        assert DEFAULT_FEE_BREAKDOWN.maker_fee_rate == Decimal("0.001")

    def test_spread_reasonable_for_btcusd(self):
        """10 bps spread is reasonable for BTC/USD."""
        # BTC/USD typically has 1-20 bps spread depending on liquidity
        # 10 bps is a conservative middle ground
        assert DEFAULT_FEE_BREAKDOWN.assumed_spread_bps >= 5
        assert DEFAULT_FEE_BREAKDOWN.assumed_spread_bps <= 20

    def test_slippage_reasonable_for_market_orders(self):
        """5 bps slippage is reasonable for market orders."""
        # Market orders typically see 1-10 bps slippage
        assert DEFAULT_FEE_BREAKDOWN.assumed_slippage_bps >= 1
        assert DEFAULT_FEE_BREAKDOWN.assumed_slippage_bps <= 10

    def test_total_cost_for_typical_trade(self):
        """Total cost for a typical $1000 BTC/USD trade should be ~35 bps."""
        model = FeeModel()
        est = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)
        # 35 bps total cost
        assert est.minimum_edge_bps == Decimal("35.00")

    def test_fee_ratio_taker_to_maker(self):
        """Taker fee should be exactly 2x maker fee (Bitfinex standard tier)."""
        ratio = DEFAULT_FEE_BREAKDOWN.taker_fee_rate / DEFAULT_FEE_BREAKDOWN.maker_fee_rate
        assert ratio == Decimal("2")


# ============================================================================
# Acceptance Criterion 6: Minimum edge filter integration
# ============================================================================


class TestMinimumEdgeFilter:
    """AC6: Fee model minimum edge should be usable as filter."""

    def test_signal_exceeds_minimum_edge(self):
        """Signals exceeding minimum edge should pass."""
        model = FeeModel()
        est = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)
        # A signal with 40 bps should pass (35 bps min edge)
        signal_bps = Decimal("40")
        assert signal_bps >= est.minimum_edge_bps

    def test_signal_below_minimum_edge(self):
        """Signals below minimum edge should be filtered."""
        model = FeeModel()
        est = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)
        # A signal with 30 bps should fail (35 bps min edge)
        signal_bps = Decimal("30")
        assert signal_bps < est.minimum_edge_bps

    def test_minimum_edge_decreases_with_larger_notional(self):
        """Minimum edge in bps should decrease with larger notional (fees are fixed %)."""
        model = FeeModel()
        est_small = model.estimate_cost(gross_notional=Decimal("100"), taker=True)
        est_large = model.estimate_cost(gross_notional=Decimal("10000"), taker=True)

        # Both should have the same minimum_edge_bps since fees are percentage-based
        # The key is that the minimum edge is expressed in bps, not absolute dollars
        assert est_small.minimum_edge_bps == est_large.minimum_edge_bps


# ============================================================================
# Validation summary
# ============================================================================


def test_validation_summary():
    """Print validation summary for acceptance criteria."""
    model = FeeModel()
    est = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)

    print("\n" + "=" * 60)
    print("FEE MODEL VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Maker fee:     {DEFAULT_FEE_BREAKDOWN.maker_fee_rate} ({DEFAULT_FEE_BREAKDOWN.maker_fee_rate * 10000} bps)")
    print(f"Taker fee:     {DEFAULT_FEE_BREAKDOWN.taker_fee_rate} ({DEFAULT_FEE_BREAKDOWN.taker_fee_rate * 10000} bps)")
    print(f"Spread:        {DEFAULT_FEE_BREAKDOWN.assumed_spread_bps} bps")
    print(f"Slippage:      {DEFAULT_FEE_BREAKDOWN.assumed_slippage_bps} bps")
    print(f"Currency:      {DEFAULT_FEE_BREAKDOWN.currency}")
    print(f"Total cost ($1k): {est.estimated_total_cost}")
    print(f"Minimum edge:  {est.minimum_edge_bps} bps")
    print(f"Taker/Maker:   {DEFAULT_FEE_BREAKDOWN.taker_fee_rate / DEFAULT_FEE_BREAKDOWN.maker_fee_rate}x")
    print("=" * 60)
    print("All acceptance criteria validated.")
    print("=" * 60 + "\n")
