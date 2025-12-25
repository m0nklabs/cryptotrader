"""Drawdown monitoring and controls.

Monitors portfolio drawdown and enforces trading pauses when limits are exceeded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal


@dataclass
class DrawdownConfig:
    """Drawdown control configuration.

    Attributes:
        max_daily_drawdown: Maximum daily drawdown before pausing (as percentage, e.g., 0.05 for 5%)
        max_total_drawdown: Maximum total drawdown before kill switch (as percentage)
        trailing_stop_percent: Trailing stop percentage for drawdown protection
    """

    max_daily_drawdown: Decimal | None = None
    max_total_drawdown: Decimal | None = None
    trailing_stop_percent: Decimal | None = None


@dataclass
class DrawdownState:
    """Tracks current drawdown state."""

    daily_peak: Decimal = Decimal("0")
    daily_current: Decimal = Decimal("0")
    total_peak: Decimal = Decimal("0")
    total_current: Decimal = Decimal("0")
    current_date: date | None = None
    trading_paused: bool = False
    kill_switch_activated: bool = False


class DrawdownMonitor:
    """Monitors portfolio drawdown and enforces limits.

    Tracks:
    - Daily drawdown (resets each day)
    - Total drawdown (since inception or last reset)
    - Trading pause states
    """

    def __init__(self, config: DrawdownConfig) -> None:
        """Initialize drawdown monitor.

        Args:
            config: Drawdown control configuration
        """
        self.config = config
        self.state = DrawdownState()

    def update_balance(self, current_balance: Decimal, timestamp: datetime | None = None) -> None:
        """Update current balance and recalculate drawdown.

        Args:
            current_balance: Current portfolio balance
            timestamp: Optional timestamp for the update (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        current_date = timestamp.date()

        # Check if we're on a new day - reset daily tracking
        if self.state.current_date is None or current_date != self.state.current_date:
            self.state.current_date = current_date
            self.state.daily_peak = current_balance
            self.state.daily_current = current_balance
            # Reset daily pause if it was set
            if self.state.trading_paused and not self.state.kill_switch_activated:
                self.state.trading_paused = False
        else:
            # Update daily peak if new high
            if current_balance > self.state.daily_peak:
                self.state.daily_peak = current_balance
            self.state.daily_current = current_balance

        # Update total tracking
        if self.state.total_peak == 0 or current_balance > self.state.total_peak:
            self.state.total_peak = current_balance
        self.state.total_current = current_balance

        # Check limits
        self._check_limits()

    def get_daily_drawdown(self) -> Decimal:
        """Get current daily drawdown as a percentage.

        Returns:
            Daily drawdown percentage (e.g., 0.05 for 5% drawdown)
        """
        if self.state.daily_peak == 0:
            return Decimal("0")

        drawdown = (self.state.daily_peak - self.state.daily_current) / self.state.daily_peak
        return drawdown

    def get_total_drawdown(self) -> Decimal:
        """Get current total drawdown as a percentage.

        Returns:
            Total drawdown percentage (e.g., 0.10 for 10% drawdown)
        """
        if self.state.total_peak == 0:
            return Decimal("0")

        drawdown = (self.state.total_peak - self.state.total_current) / self.state.total_peak
        return drawdown

    def is_daily_drawdown_exceeded(self) -> bool:
        """Check if daily drawdown limit is exceeded.

        Returns:
            True if daily drawdown exceeds configured limit
        """
        if self.config.max_daily_drawdown is None:
            return False

        return self.get_daily_drawdown() >= self.config.max_daily_drawdown

    def is_total_drawdown_exceeded(self) -> bool:
        """Check if total drawdown limit is exceeded.

        Returns:
            True if total drawdown exceeds configured limit
        """
        if self.config.max_total_drawdown is None:
            return False

        return self.get_total_drawdown() >= self.config.max_total_drawdown

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed.

        Returns:
            False if trading is paused or kill switch is activated
        """
        return not self.state.trading_paused and not self.state.kill_switch_activated

    def check_daily_drawdown(self, current_equity: Decimal, peak_equity: Decimal) -> bool:
        """Check if daily drawdown is within limits.

        Args:
            current_equity: Current equity value
            peak_equity: Peak equity value for the day

        Returns:
            True if within limits, False if exceeded
        """
        if self.config.max_daily_drawdown is None:
            return True

        if peak_equity == 0:
            return True

        drawdown = (peak_equity - current_equity) / peak_equity

        return drawdown <= self.config.max_daily_drawdown

    def check_limits(self, current_equity: Decimal, peak_equity: Decimal) -> bool:
        """Check if equity is within drawdown limits.

        Args:
            current_equity: Current equity value
            peak_equity: Peak equity value

        Returns:
            True if within limits, False if exceeded
        """
        if self.config.max_daily_drawdown is None:
            return True

        if peak_equity == 0:
            return True

        drawdown = (peak_equity - current_equity) / peak_equity

        return drawdown <= self.config.max_daily_drawdown

    def _check_limits(self) -> None:
        """Internal method to check limits and update pause states."""
        # Check daily drawdown
        if self.is_daily_drawdown_exceeded():
            self.state.trading_paused = True

        # Check total drawdown (kill switch)
        if self.is_total_drawdown_exceeded():
            self.state.trading_paused = True
            self.state.kill_switch_activated = True

    def reset_daily(self) -> None:
        """Reset daily drawdown tracking (called at start of new day)."""
        self.state.daily_peak = self.state.daily_current
        if not self.state.kill_switch_activated:
            self.state.trading_paused = False

    def reset_total(self) -> None:
        """Reset total drawdown tracking (use with caution)."""
        self.state.total_peak = self.state.total_current
        self.state.kill_switch_activated = False
        if not self.is_daily_drawdown_exceeded():
            self.state.trading_paused = False
