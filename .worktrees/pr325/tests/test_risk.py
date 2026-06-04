"""Tests for risk management module."""

from decimal import Decimal

import pytest

from core.risk import (
    DrawdownConfig,
    DrawdownMonitor,
    ExposureChecker,
    ExposureLimits,
    PositionSize,
    calculate_position_size,
)


# ========== Position Sizing Tests ==========


class TestPositionSizing:
    """Tests for position sizing algorithms."""

    def test_position_size_fixed_method(self) -> None:
        """Test fixed fractional position sizing."""
        config = PositionSize(method="fixed", portfolio_percent=Decimal("0.01"))
        # Risk 1% of $10,000 = $100
        # Entry at $100, stop at $99 = $1 risk per unit
        # Position size = $100 / $1 = 100 units
        size = calculate_position_size(config, Decimal("10000"), Decimal("100"), Decimal("99"))
        assert size == Decimal("100")

    def test_position_size_kelly_method(self) -> None:
        """Test Kelly criterion position sizing."""
        config = PositionSize(
            method="kelly",
            win_rate=Decimal("0.6"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            kelly_fraction=Decimal("0.5"),
        )
        # Kelly formula: f* = (p * b - q) / b
        # p = 0.6, q = 0.4, b = 100/50 = 2
        # f* = (0.6 * 2 - 0.4) / 2 = 0.4
        # Fractional Kelly = 0.4 * 0.5 = 0.2 (20% of portfolio)
        # Risk 20% of $1000 = $200
        # Entry at $50, stop at $40 = $10 risk per unit
        # Position size = $200 / $10 = 20 units
        size = calculate_position_size(config, Decimal("1000"), Decimal("50"), Decimal("40"))
        assert size == Decimal("20")

    def test_position_size_atr_method(self) -> None:
        """Test ATR-based position sizing."""
        config = PositionSize(method="atr", atr_multiplier=Decimal("0.02"))
        # Risk 2% of $1000 = $20
        # ATR = $10
        # Position size = $20 / $10 = 2 units
        size = calculate_position_size(config, Decimal("1000"), Decimal("50"), Decimal("40"), Decimal("10"))
        assert size == Decimal("2")

    def test_position_size_missing_atr_raises(self) -> None:
        """Test that ATR method raises if ATR not provided."""
        config = PositionSize(method="atr", atr_multiplier=Decimal("0.01"))
        with pytest.raises(ValueError, match="ATR is required"):
            calculate_position_size(config, Decimal("1000"), Decimal("50"), Decimal("40"))

    def test_position_size_zero_risk_raises(self) -> None:
        """Test that zero risk per unit raises error."""
        config = PositionSize(method="fixed", portfolio_percent=Decimal("0.01"))
        with pytest.raises(ValueError, match="Risk per unit cannot be zero"):
            calculate_position_size(config, Decimal("10000"), Decimal("100"), Decimal("100"))

    def test_position_size_fixed_missing_percent_raises(self) -> None:
        """Test that fixed method raises if portfolio_percent not provided."""
        config = PositionSize(method="fixed")
        with pytest.raises(ValueError, match="portfolio_percent is required"):
            calculate_position_size(config, Decimal("10000"), Decimal("100"), Decimal("99"))

    def test_position_size_kelly_missing_params_raises(self) -> None:
        """Test that Kelly method raises if required params not provided."""
        config = PositionSize(method="kelly")
        with pytest.raises(ValueError, match="win_rate, avg_win, and avg_loss are required"):
            calculate_position_size(config, Decimal("1000"), Decimal("50"), Decimal("40"))


# ========== Exposure Limits Tests ==========


class TestExposureLimits:
    """Tests for exposure limit checks."""

    def test_check_position_size_within_limit(self) -> None:
        """Test position size check passes when within limit."""
        limits = ExposureLimits(max_position_size_per_symbol=Decimal("10000"))
        checker = ExposureChecker(limits)

        allowed, reason = checker.check_position_size("BTC/USD", Decimal("5000"))
        assert allowed is True
        assert reason is None

    def test_check_position_size_exceeds_limit(self) -> None:
        """Test position size check fails when exceeds limit."""
        limits = ExposureLimits(max_position_size_per_symbol=Decimal("10000"))
        checker = ExposureChecker(limits)

        allowed, reason = checker.check_position_size("BTC/USD", Decimal("15000"))
        assert allowed is False
        assert "exceeds max" in reason

    def test_check_position_size_no_limit(self) -> None:
        """Test position size check passes when no limit set."""
        limits = ExposureLimits()
        checker = ExposureChecker(limits)

        allowed, reason = checker.check_position_size("BTC/USD", Decimal("999999"))
        assert allowed is True
        assert reason is None

    def test_check_total_exposure_within_limit(self) -> None:
        """Test total exposure check passes when within limit."""
        limits = ExposureLimits(max_total_exposure=Decimal("0.95"))  # 95%
        checker = ExposureChecker(limits)

        # Current exposure: $8000, new position: $1000, portfolio: $10000
        # Total: $9000 / $10000 = 90% < 95%
        allowed, reason = checker.check_total_exposure(Decimal("8000"), Decimal("10000"), Decimal("1000"))
        assert allowed is True
        assert reason is None

    def test_check_total_exposure_exceeds_limit(self) -> None:
        """Test total exposure check fails when exceeds limit."""
        limits = ExposureLimits(max_total_exposure=Decimal("0.95"))  # 95%
        checker = ExposureChecker(limits)

        # Current exposure: $9000, new position: $2000, portfolio: $10000
        # Total: $11000 / $10000 = 110% > 95%
        allowed, reason = checker.check_total_exposure(Decimal("9000"), Decimal("10000"), Decimal("2000"))
        assert allowed is False
        assert "would exceed max" in reason

    def test_check_position_count_within_limit(self) -> None:
        """Test position count check passes when within limit."""
        limits = ExposureLimits(max_positions=10)
        checker = ExposureChecker(limits)

        allowed, reason = checker.check_position_count(5)
        assert allowed is True
        assert reason is None

    def test_check_position_count_at_limit(self) -> None:
        """Test position count check fails when at limit."""
        limits = ExposureLimits(max_positions=10)
        checker = ExposureChecker(limits)

        allowed, reason = checker.check_position_count(10)
        assert allowed is False
        assert "Max positions" in reason

    def test_check_all_passes(self) -> None:
        """Test all checks pass when all limits satisfied."""
        limits = ExposureLimits(
            max_position_size_per_symbol=Decimal("5000"),
            max_total_exposure=Decimal("0.95"),
            max_positions=10,
        )
        checker = ExposureChecker(limits)

        allowed, reasons = checker.check_all(
            symbol="BTC/USD",
            position_value=Decimal("3000"),
            current_exposure=Decimal("5000"),
            portfolio_value=Decimal("10000"),
            current_positions=5,
        )
        assert allowed is True
        assert len(reasons) == 0

    def test_check_all_fails_multiple(self) -> None:
        """Test all checks fail when multiple limits violated."""
        limits = ExposureLimits(
            max_position_size_per_symbol=Decimal("2000"),
            max_total_exposure=Decimal("0.50"),
            max_positions=5,
        )
        checker = ExposureChecker(limits)

        allowed, reasons = checker.check_all(
            symbol="BTC/USD",
            position_value=Decimal("3000"),
            current_exposure=Decimal("4000"),
            portfolio_value=Decimal("10000"),
            current_positions=5,
        )
        assert allowed is False
        assert len(reasons) == 3  # All three checks should fail


# ========== Drawdown Monitor Tests ==========


class TestDrawdownMonitor:
    """Tests for drawdown monitoring."""

    def test_drawdown_monitor_initialization(self) -> None:
        """Test drawdown monitor initialization."""
        config = DrawdownConfig(max_daily_drawdown=Decimal("0.05"))
        monitor = DrawdownMonitor(config)

        assert monitor.config.max_daily_drawdown == Decimal("0.05")
        assert monitor.state.daily_peak == Decimal("0")
        assert monitor.state.trading_paused is False

    def test_drawdown_monitor_daily_check(self) -> None:
        """Test daily drawdown check."""
        config = DrawdownConfig(max_daily_drawdown=Decimal("0.05"))
        monitor = DrawdownMonitor(config)

        # 5% drawdown should be at the limit (not exceeded)
        result = monitor.check_daily_drawdown(Decimal("950"), Decimal("1000"))
        assert result is True

        # More than 5% should fail
        result = monitor.check_daily_drawdown(Decimal("940"), Decimal("1000"))
        assert result is False

    def test_drawdown_monitor_update_balance(self) -> None:
        """Test updating balance and tracking drawdown."""
        config = DrawdownConfig(max_daily_drawdown=Decimal("0.05"))
        monitor = DrawdownMonitor(config)

        # Initialize with starting balance
        monitor.update_balance(Decimal("1000"))
        assert monitor.state.daily_peak == Decimal("1000")
        assert monitor.state.total_peak == Decimal("1000")

        # Update to higher balance
        monitor.update_balance(Decimal("1100"))
        assert monitor.state.daily_peak == Decimal("1100")
        assert monitor.state.total_peak == Decimal("1100")

        # Update to lower balance (within limit)
        monitor.update_balance(Decimal("1050"))
        assert monitor.get_daily_drawdown() < Decimal("0.05")
        assert monitor.state.trading_paused is False

    def test_drawdown_monitor_exceeds_daily_limit(self) -> None:
        """Test that trading pauses when daily limit exceeded."""
        config = DrawdownConfig(max_daily_drawdown=Decimal("0.05"))
        monitor = DrawdownMonitor(config)

        monitor.update_balance(Decimal("1000"))
        monitor.update_balance(Decimal("940"))  # 6% drawdown

        assert monitor.is_daily_drawdown_exceeded() is True
        assert monitor.state.trading_paused is True
        assert monitor.is_trading_allowed() is False

    def test_drawdown_monitor_total_drawdown(self) -> None:
        """Test total drawdown tracking."""
        config = DrawdownConfig(max_total_drawdown=Decimal("0.20"))
        monitor = DrawdownMonitor(config)

        monitor.update_balance(Decimal("1000"))
        assert monitor.get_total_drawdown() == Decimal("0")

        monitor.update_balance(Decimal("850"))  # 15% drawdown
        assert monitor.get_total_drawdown() == Decimal("0.15")
        assert monitor.is_total_drawdown_exceeded() is False

        monitor.update_balance(Decimal("750"))  # 25% drawdown
        assert monitor.is_total_drawdown_exceeded() is True
        assert monitor.state.kill_switch_activated is True

    def test_drawdown_monitor_check_limits(self) -> None:
        """Test check_limits method."""
        config = DrawdownConfig(max_daily_drawdown=Decimal("0.05"))
        monitor = DrawdownMonitor(config)

        # Within limit
        result = monitor.check_limits(Decimal("960"), Decimal("1000"))
        assert result is True

        # At limit (should pass as it's <, not <=)
        result = monitor.check_limits(Decimal("950"), Decimal("1000"))
        assert result is True

        # Exceeds limit
        result = monitor.check_limits(Decimal("940"), Decimal("1000"))
        assert result is False

    def test_drawdown_monitor_daily_reset(self) -> None:
        """Test daily reset functionality."""
        config = DrawdownConfig(max_daily_drawdown=Decimal("0.05"))
        monitor = DrawdownMonitor(config)

        monitor.update_balance(Decimal("1000"))
        monitor.update_balance(Decimal("940"))  # Trigger pause

        assert monitor.state.trading_paused is True

        # Simulate daily reset
        monitor.reset_daily()
        assert monitor.state.trading_paused is False

    def test_drawdown_monitor_no_limits(self) -> None:
        """Test monitor with no limits set."""
        config = DrawdownConfig()
        monitor = DrawdownMonitor(config)

        monitor.update_balance(Decimal("1000"))
        monitor.update_balance(Decimal("1"))  # 99.9% drawdown

        assert monitor.is_daily_drawdown_exceeded() is False
        assert monitor.is_total_drawdown_exceeded() is False
        assert monitor.is_trading_allowed() is True

    def test_drawdown_monitor_boundary_consistency(self) -> None:
        """Test that boundary conditions are consistent across methods."""
        config = DrawdownConfig(max_daily_drawdown=Decimal("0.05"))
        monitor = DrawdownMonitor(config)

        # At exactly 5% drawdown, should NOT be exceeded
        # check_daily_drawdown should return True (within limits)
        # is_daily_drawdown_exceeded should return False (not exceeded)
        result = monitor.check_daily_drawdown(Decimal("950"), Decimal("1000"))
        assert result is True, "At limit should be within limits"

        # Simulate the same scenario via update_balance
        monitor.update_balance(Decimal("1000"))
        monitor.update_balance(Decimal("950"))
        assert monitor.is_daily_drawdown_exceeded() is False, "At limit should not be exceeded"
        assert monitor.is_trading_allowed() is True, "Trading should be allowed at limit"

        # Just over 5% should be exceeded
        monitor2 = DrawdownMonitor(config)
        monitor2.update_balance(Decimal("1000"))
        monitor2.update_balance(Decimal("949"))  # 5.1% drawdown
        assert monitor2.is_daily_drawdown_exceeded() is True, "Over limit should be exceeded"
        assert monitor2.is_trading_allowed() is False, "Trading should be paused over limit"
