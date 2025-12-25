"""Safety checks for automation engine.

Implements concrete safety checks including kill switch, position limits,
cooldowns, daily limits, and balance verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol, Sequence

from core.types import OrderIntent

from .rules import AutomationConfig, TradeHistory


@dataclass(frozen=True)
class SafetyResult:
    ok: bool
    reason: str


class SafetyCheck(Protocol):
    def check(self, *, intent: OrderIntent) -> SafetyResult:
        """Return whether intent is safe to execute."""


def run_safety_checks(*, checks: Sequence[SafetyCheck], intent: OrderIntent) -> SafetyResult:
    for check in checks:
        res = check.check(intent=intent)
        if not res.ok:
            return res
    return SafetyResult(ok=True, reason="ok")


# ========== Concrete Safety Check Implementations ==========


@dataclass
class KillSwitchCheck:
    """Check if automation is globally enabled (kill switch)."""

    config: AutomationConfig

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        if not self.config.enabled:
            return SafetyResult(ok=False, reason="Kill switch: automation globally disabled")
        if not self.config.is_symbol_enabled(intent.symbol):
            return SafetyResult(ok=False, reason=f"Kill switch: automation disabled for {intent.symbol}")
        return SafetyResult(ok=True, reason="Kill switch: enabled")


@dataclass
class PositionSizeCheck:
    """Check if position size is within limits."""

    config: AutomationConfig
    current_position_value: Decimal = Decimal("0")  # Current position value for this symbol

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        symbol_config = self.config.get_symbol_config(intent.symbol)

        # Check symbol-specific max position size
        if symbol_config.max_position_size is not None:
            # TODO: Implement proper position value calculation with current market price
            # For now, simplified implementation assumes amount is in quote currency
            position_value = intent.amount
            total_position = self.current_position_value + position_value

            if total_position > symbol_config.max_position_size:
                return SafetyResult(
                    ok=False,
                    reason=f"Position size limit exceeded: {total_position} > {symbol_config.max_position_size}",
                )

        return SafetyResult(ok=True, reason="Position size within limits")


@dataclass
class CooldownCheck:
    """Check if cooldown period has passed since last trade."""

    config: AutomationConfig
    trade_history: TradeHistory

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        symbol_config = self.config.get_symbol_config(intent.symbol)

        if symbol_config.cooldown_seconds <= 0:
            return SafetyResult(ok=True, reason="No cooldown configured")

        last_trade_time = self.trade_history.get_last_trade_time(intent.symbol)
        if last_trade_time is None:
            return SafetyResult(ok=True, reason="No previous trades")

        time_since_last = datetime.now() - last_trade_time
        cooldown = timedelta(seconds=symbol_config.cooldown_seconds)

        if time_since_last < cooldown:
            remaining = cooldown - time_since_last
            return SafetyResult(
                ok=False,
                reason=f"Cooldown active: {remaining.total_seconds():.0f}s remaining",
            )

        return SafetyResult(ok=True, reason="Cooldown period passed")


@dataclass
class DailyTradeCountCheck:
    """Check if daily trade count is within limits."""

    config: AutomationConfig
    trade_history: TradeHistory

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        symbol_config = self.config.get_symbol_config(intent.symbol)

        # Check symbol-specific limit
        if symbol_config.max_daily_trades is not None:
            symbol_count = self.trade_history.get_daily_trade_count(intent.symbol)
            if symbol_count >= symbol_config.max_daily_trades:
                return SafetyResult(
                    ok=False,
                    reason=f"Daily trade limit for {intent.symbol}: {symbol_count}/{symbol_config.max_daily_trades}",
                )

        # Check global limit
        if self.config.max_daily_trades_global is not None:
            global_count = self.trade_history.get_daily_trade_count()
            if global_count >= self.config.max_daily_trades_global:
                return SafetyResult(
                    ok=False,
                    reason=f"Global daily trade limit: {global_count}/{self.config.max_daily_trades_global}",
                )

        return SafetyResult(ok=True, reason="Daily trade count within limits")


@dataclass
class BalanceCheck:
    """Check if balance meets minimum requirements."""

    config: AutomationConfig
    current_balance: Decimal

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        if self.config.min_balance_required is None:
            return SafetyResult(ok=True, reason="No minimum balance required")

        if self.current_balance < self.config.min_balance_required:
            return SafetyResult(
                ok=False,
                reason=f"Insufficient balance: {self.current_balance} < {self.config.min_balance_required}",
            )

        # Also check if we have enough to execute this order
        if self.current_balance < intent.amount:
            return SafetyResult(
                ok=False,
                reason=f"Insufficient balance for order: {self.current_balance} < {intent.amount}",
            )

        return SafetyResult(ok=True, reason="Balance sufficient")


@dataclass
class DailyLossCheck:
    """Check if daily loss is within limits."""

    config: AutomationConfig
    daily_pnl: Decimal  # Positive = profit, Negative = loss

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        # Check absolute loss limit
        if self.config.max_daily_loss is not None:
            if self.daily_pnl < -self.config.max_daily_loss:
                return SafetyResult(
                    ok=False,
                    reason=f"Daily loss limit exceeded: {-self.daily_pnl} > {self.config.max_daily_loss}",
                )

        return SafetyResult(ok=True, reason="Daily loss within limits")


@dataclass
class SlippageCheck:
    """Check if expected slippage is within acceptable limits."""

    config: AutomationConfig
    expected_slippage_bps: int = 0  # Expected slippage in basis points

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        symbol_config = self.config.get_symbol_config(intent.symbol)

        if symbol_config.max_slippage_bps is None:
            return SafetyResult(ok=True, reason="No slippage limit configured")

        if self.expected_slippage_bps > symbol_config.max_slippage_bps:
            return SafetyResult(
                ok=False,
                reason=f"Expected slippage too high: {self.expected_slippage_bps}bps > {symbol_config.max_slippage_bps}bps",
            )

        return SafetyResult(ok=True, reason="Slippage within acceptable limits")
