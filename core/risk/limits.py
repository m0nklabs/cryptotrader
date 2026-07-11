"""Exposure limit checks for risk management.

Enforces position size and exposure limits to prevent over-concentration.
"""

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


@dataclass
class ExposureLimits:
    """Exposure limit configuration.

    Attributes:
        max_position_size_per_symbol: Maximum position size for a single symbol (in quote currency)
        max_total_exposure: Maximum total portfolio exposure (as percentage, e.g., 0.95 for 95%)
        max_correlated_exposure: Maximum exposure to correlated assets (as percentage)
        max_positions: Maximum number of open positions
    """

    max_position_size_per_symbol: Decimal | None = None
    max_total_exposure: Decimal | None = None
    max_correlated_exposure: Decimal | None = None
    max_positions: int | None = None


class ExposureChecker:
    """Checks exposure limits before order execution."""

    def __init__(self, limits: ExposureLimits) -> None:
        """Initialize exposure checker.

        Args:
            limits: Exposure limit configuration
        """
        self.limits = limits

    def check_position_size(self, symbol: str, position_value: Decimal) -> tuple[bool, str | None]:
        """Check if position size is within limits for a symbol.

        Args:
            symbol: Trading symbol
            position_value: Proposed position value in quote currency

        Returns:
            Tuple of (is_allowed, reason_if_rejected)
        """
        if self.limits.max_position_size_per_symbol is None:
            return True, None

        if position_value > self.limits.max_position_size_per_symbol:
            return (
                False,
                f"Position size {position_value} exceeds max {self.limits.max_position_size_per_symbol} for {symbol}",
            )

        return True, None

    def check_total_exposure(
        self, current_exposure: Decimal, portfolio_value: Decimal, new_position_value: Decimal
    ) -> tuple[bool, str | None]:
        """Check if total exposure is within limits.

        Args:
            current_exposure: Current total exposure across all positions
            portfolio_value: Total portfolio value
            new_position_value: Value of new position to add

        Returns:
            Tuple of (is_allowed, reason_if_rejected)
        """
        if self.limits.max_total_exposure is None:
            return True, None

        if portfolio_value == 0:
            return False, "Portfolio value is zero"

        total_exposure = current_exposure + new_position_value
        exposure_percent = total_exposure / portfolio_value

        if exposure_percent > self.limits.max_total_exposure:
            max_exposure_value = portfolio_value * self.limits.max_total_exposure
            return (
                False,
                f"Total exposure {total_exposure} would exceed max {max_exposure_value} "
                f"({self.limits.max_total_exposure * 100}% of portfolio)",
            )

        return True, None

    def check_position_count(self, current_positions: int) -> tuple[bool, str | None]:
        """Check if number of positions is within limits.

        Args:
            current_positions: Current number of open positions

        Returns:
            Tuple of (is_allowed, reason_if_rejected)
        """
        if self.limits.max_positions is None:
            return True, None

        if current_positions >= self.limits.max_positions:
            return False, f"Max positions {self.limits.max_positions} reached"

        return True, None

    def check_all(
        self,
        symbol: str,
        position_value: Decimal,
        current_exposure: Decimal,
        portfolio_value: Decimal,
        current_positions: int,
    ) -> tuple[bool, list[str]]:
        """Check all exposure limits.

        Args:
            symbol: Trading symbol
            position_value: Proposed position value
            current_exposure: Current total exposure
            portfolio_value: Total portfolio value
            current_positions: Current number of positions

        Returns:
            Tuple of (all_checks_passed, list_of_rejection_reasons)

        Notes:
            ``check_all`` retains its original aggregate behavior (per-symbol
            position size + total exposure + position count) so existing
            callers and tests that depend on the three-reason contract are
            preserved. Gate orchestration uses the narrower
            ``check_portfolio_exposure`` plus the per-symbol
            ``check_position_size`` instead, so each gate owns a single
            concern and no single gate collapses several safety limits.
        """
        reasons = []

        # Check position size
        allowed, reason = self.check_position_size(symbol, position_value)
        if not allowed and reason:
            reasons.append(reason)

        # Check total exposure
        allowed, reason = self.check_total_exposure(current_exposure, portfolio_value, position_value)
        if not allowed and reason:
            reasons.append(reason)

        # Check position count
        allowed, reason = self.check_position_count(current_positions)
        if not allowed and reason:
            reasons.append(reason)

        return len(reasons) == 0, reasons

    def check_portfolio_exposure(
        self,
        current_exposure: Decimal,
        portfolio_value: Decimal,
        new_position_value: Decimal,
        current_positions: int,
    ) -> tuple[bool, list[str]]:
        """Check portfolio-wide exposure and position count.

        Deliberately excludes per-symbol position size, which is owned by
        the risk-limit gate. This keeps gate responsibilities distinct:
        ``exposure`` enforces portfolio-level limits and ``risk_limit``
        enforces per-symbol notional. Mixing them collapses multiple
        auditable safety contracts into one gate and hides which limit
        actually rejected an order.

        Args:
            current_exposure: Current total exposure across all positions.
            portfolio_value: Total portfolio value.
            new_position_value: Quote-notional value of the proposed position.
            current_positions: Number of currently open positions.

        Returns:
            Tuple of (all_portfolio_checks_passed, list_of_rejection_reasons).
        """
        reasons: list[str] = []

        allowed, reason = self.check_total_exposure(
            current_exposure, portfolio_value, new_position_value
        )
        if not allowed and reason:
            reasons.append(reason)

        allowed, reason = self.check_position_count(current_positions)
        if not allowed and reason:
            reasons.append(reason)

        return len(reasons) == 0, reasons
