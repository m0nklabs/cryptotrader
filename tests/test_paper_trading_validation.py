"""Tests for paper trading execution validation module.

Covers:
- FeeModelValidator: maker/taker, spread, slippage, cost estimates, funding
- PartialFillValidator: fill distribution, fill qty, fill ratio
- PositionSizingValidator: fixed, kelly, ATR, executor integration
- RiskGateValidator: drawdown, exposure, concurrent positions, trading pause
- TradeLoggingValidator: execution logging, decision traceability, rejections, event format
- IntegrationValidator: full trade cycle, cost deduction, executor summary
- validate_paper_trading_execution: end-to-end validation
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.paper_trading.validation import (
    FeeModelValidator,
    IntegrationValidator,
    PartialFillValidator,
    PositionSizingValidator,
    RiskGateValidator,
    TradeLoggingValidator,
    ValidationReport,
    ValidationResult,
    validate_paper_trading_execution,
)


# ============================================================================
# FeeModelValidator tests
# ============================================================================


class TestFeeModelValidator:
    def test_validate_maker_taker(self):
        validator = FeeModelValidator()
        result = validator.validate_maker_taker()
        assert result.passed
        assert "Maker" in result.message

    def test_validate_spread_slippage(self):
        validator = FeeModelValidator()
        result = validator.validate_spread_slippage()
        assert result.passed
        assert "bps" in result.message

    def test_validate_cost_estimate(self):
        validator = FeeModelValidator()
        result = validator.validate_cost_estimate()
        assert result.passed
        assert "Taker" in result.message

    def test_validate_funding_rate(self):
        validator = FeeModelValidator()
        result = validator.validate_funding_rate()
        assert result.passed
        assert "funding" in result.message.lower()

    def test_validate_with_custom_fee_model(self):
        from core.fees.model import DEFAULT_FEE_BREAKDOWN, FeeModel

        custom = FeeModel(
            breakdown=DEFAULT_FEE_BREAKDOWN.__class__(
                currency="USD",
                maker_fee_rate=Decimal("0.0005"),
                taker_fee_rate=Decimal("0.0015"),
                assumed_spread_bps=5,
                assumed_slippage_bps=3,
            ),
        )
        validator = FeeModelValidator(fee_model=custom)
        result = validator.validate_maker_taker()
        assert result.passed

    def test_validate_cost_estimate_custom_notional(self):
        validator = FeeModelValidator()
        result = validator.validate_cost_estimate(notional=Decimal("10000"))
        assert result.passed


# ============================================================================
# PartialFillValidator tests
# ============================================================================


class TestPartialFillValidator:
    def test_validate_fill_status_distribution(self):
        from core.execution.paper import PaperExecutor

        executor = PaperExecutor()
        validator = PartialFillValidator(executor)
        result = validator.validate_fill_status_distribution()
        assert result.passed

    def test_validate_partial_fill_qty(self):
        from core.execution.paper import PaperExecutor

        executor = PaperExecutor()
        validator = PartialFillValidator(executor)
        result = validator.validate_partial_fill_qty()
        assert result.passed

    def test_validate_fill_ratio(self):
        from core.execution.paper import PaperExecutor

        executor = PaperExecutor()
        validator = PartialFillValidator(executor)
        result = validator.validate_fill_ratio()
        assert result.passed
        assert "fill_ratio" in result.message.lower()


# ============================================================================
# PositionSizingValidator tests
# ============================================================================


class TestPositionSizingValidator:
    def test_validate_fixed_sizing(self):
        validator = PositionSizingValidator()
        result = validator.validate_fixed_sizing()
        assert result.passed
        assert "2.50" in result.message

    def test_validate_kelly_sizing(self):
        validator = PositionSizingValidator()
        result = validator.validate_kelly_sizing()
        assert result.passed
        assert "10.00" in result.message

    def test_validate_atr_sizing(self):
        validator = PositionSizingValidator()
        result = validator.validate_atr_sizing()
        assert result.passed
        assert "200" in result.message

    def test_validate_position_sizing_with_executor(self):
        validator = PositionSizingValidator()
        result = validator.validate_position_sizing_with_executor()
        assert result.passed


# ============================================================================
# RiskGateValidator tests
# ============================================================================


class TestRiskGateValidator:
    def test_validate_daily_drawdown(self):
        validator = RiskGateValidator()
        result = validator.validate_daily_drawdown()
        assert result.passed

    def test_validate_total_drawdown(self):
        validator = RiskGateValidator()
        result = validator.validate_total_drawdown()
        assert result.passed

    def test_validate_exposure_limits(self):
        validator = RiskGateValidator()
        result = validator.validate_exposure_limits()
        assert result.passed

    def test_validate_concurrent_positions(self):
        validator = RiskGateValidator()
        result = validator.validate_concurrent_positions()
        assert result.passed
        assert "3 concurrent" in result.message

    def test_validate_drawdown_trading_pause(self):
        validator = RiskGateValidator()
        result = validator.validate_drawdown_trading_pause()
        assert result.passed


# ============================================================================
# TradeLoggingValidator tests
# ============================================================================


class TestTradeLoggingValidator:
    def test_validate_trade_execution_logging(self):
        validator = TradeLoggingValidator()
        result = validator.validate_trade_execution_logging()
        assert result.passed

    def test_validate_decision_traceability(self):
        validator = TradeLoggingValidator()
        result = validator.validate_decision_traceability()
        assert result.passed

    def test_validate_rejection_logging(self):
        validator = TradeLoggingValidator()
        result = validator.validate_rejection_logging()
        assert result.passed

    def test_validate_audit_event_format(self):
        validator = TradeLoggingValidator()
        result = validator.validate_audit_event_format()
        assert result.passed


# ============================================================================
# IntegrationValidator tests
# ============================================================================


class TestIntegrationValidator:
    def test_validate_full_trade_cycle(self):
        validator = IntegrationValidator()
        result = validator.validate_full_trade_cycle()
        assert result.passed

    def test_validate_cost_deduction_from_pnl(self):
        validator = IntegrationValidator()
        result = validator.validate_cost_deduction_from_pnl()
        assert result.passed

    def test_validate_executor_summary(self):
        validator = IntegrationValidator()
        result = validator.validate_executor_summary()
        assert result.passed


# ============================================================================
# ValidationReport tests
# ============================================================================


class TestValidationReport:
    def test_all_passed(self):
        report = ValidationReport(
            checks=[
                ValidationResult(name="a", passed=True, message="ok"),
                ValidationResult(name="b", passed=True, message="ok"),
            ],
        )
        assert report.all_passed
        assert report.passed_count == 2
        assert report.failed_count == 0

    def test_some_failed(self):
        report = ValidationReport(
            checks=[
                ValidationResult(name="a", passed=True, message="ok"),
                ValidationResult(name="b", passed=False, message="fail"),
            ],
        )
        assert not report.all_passed
        assert report.passed_count == 1
        assert report.failed_count == 1

    def test_summary_format(self):
        report = ValidationReport(
            checks=[
                ValidationResult(name="test_check", passed=True, message="works"),
            ],
        )
        summary = report.summary()
        assert "test_check" in summary
        assert "PASS" in summary
        assert "ALL PASSED" in summary


# ============================================================================
# End-to-end validation test
# ============================================================================


class TestValidatePaperTradingExecution:
    def test_all_checks_pass(self):
        report = validate_paper_trading_execution()
        assert report.all_passed
        assert report.passed_count == 23
        assert report.failed_count == 0

    def test_report_has_all_sections(self):
        report = validate_paper_trading_execution()
        names = {c.name for c in report.checks}
        # Fee model
        assert "maker_taker_rates" in names
        assert "spread_slippage" in names
        assert "cost_estimate_consistency" in names
        assert "funding_rate_coverage" in names
        # Partial fills
        assert "fill_status_distribution" in names
        assert "partial_fill_qty" in names
        assert "fill_ratio" in names
        # Position sizing
        assert "fixed_sizing" in names
        assert "kelly_sizing" in names
        assert "atr_sizing" in names
        assert "executor_position" in names
        # Risk gates
        assert "daily_drawdown" in names
        assert "total_drawdown" in names
        assert "exposure_limits" in names
        assert "concurrent_positions" in names
        assert "trading_pause" in names
        # Trade logging
        assert "trade_execution_log" in names
        assert "decision_traceability" in names
        assert "rejection_logging" in names
        assert "event_format" in names
        # Integration
        assert "full_trade_cycle" in names
        assert "cost_deduction" in names
        assert "executor_summary" in names

    def test_timestamp_is_set(self):
        report = validate_paper_trading_execution()
        assert report.timestamp is not None
