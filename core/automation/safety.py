"""Safety checks for automation engine.

Implements concrete safety checks including kill switch, position limits,
cooldowns, daily limits, and balance verification.

All timestamps use timezone-aware UTC datetimes for consistency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    """Check if position size is within limits.

    Position values are in quote currency (e.g., USDT).
    The notional value of an order is amount * current_price.
    """

    config: AutomationConfig
    current_position_value: Decimal = Decimal("0")  # Current position value in quote currency for this symbol
    current_price: Decimal = Decimal("1")  # Current market price in quote currency per unit

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        symbol_config = self.config.get_symbol_config(intent.symbol)

        # Check symbol-specific max position size
        if symbol_config.max_position_size is not None:
            # Compute notional value of this order in quote currency
            order_notional = intent.amount * self.current_price

            # BUY orders increase position value, SELL orders decrease it
            if intent.side == "SELL":
                total_position = self.current_position_value - order_notional
            else:
                total_position = self.current_position_value + order_notional

            if total_position > symbol_config.max_position_size:
                return SafetyResult(
                    ok=False,
                    reason=f"Position size limit exceeded: {total_position:.2f} > {symbol_config.max_position_size:.2f} (order notional: {order_notional:.2f})",
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

        time_since_last = datetime.now(timezone.utc) - last_trade_time
        cooldown = timedelta(seconds=symbol_config.cooldown_seconds)

        if time_since_last < cooldown:
            remaining = cooldown - time_since_last
            return SafetyResult(
                ok=False,
                reason=f"Cooldown active: {remaining.total_seconds():.0f}s remaining",
            )

        return SafetyResult(ok=True, reason="Cooldown period passed")

    def is_cooldown_check_active(self, intent: OrderIntent) -> bool:
        """Return True if cooldown is currently active for this intent."""
        result = self.check(intent=intent)
        return not result.ok


class CooldownCheckReference:
    """Optional reference to a CooldownCheck for unified cooldown tracking.

    When provided, SignalDeduplication defers to this check for cooldown
    boundary decisions, ensuring both mechanisms agree on whether cooldown
    is active.
    """

    def __init__(self, cooldown_check: CooldownCheck) -> None:
        self.cooldown_check = cooldown_check

    def is_cooldown_active(self, *, intent: OrderIntent) -> bool:
        """Return True if the referenced CooldownCheck says cooldown is active."""
        result = self.cooldown_check.check(intent=intent)
        return not result.ok

    def get_cooldown_reason(self, *, intent: OrderIntent) -> str:
        """Return the cooldown reason string from the referenced check."""
        result = self.cooldown_check.check(intent=intent)
        return result.reason


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
    """Check if balance meets minimum requirements.

    Compares notional value (amount * current_price) against balance
    for BUY orders, and amount (base currency units) against balance
    for SELL orders.
    """

    config: AutomationConfig
    current_balance: Decimal
    current_price: Decimal = Decimal("1")  # Current market price in quote currency per unit

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        if self.config.min_balance_required is None:
            return SafetyResult(ok=True, reason="No minimum balance required")

        if self.current_balance < self.config.min_balance_required:
            return SafetyResult(
                ok=False,
                reason=f"Insufficient balance: {self.current_balance} < {self.config.min_balance_required}",
            )

        # Compare notional value (amount * price) against balance
        notional = intent.amount * self.current_price
        if self.current_balance < notional:
            return SafetyResult(
                ok=False,
                reason=f"Insufficient balance for order: {self.current_balance} < {notional:.2f} (notional: {intent.amount} units * {self.current_price} price)",
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


@dataclass
class DrawdownCheck:
    """Check if drawdown is within limits before executing a trade."""

    trading_paused: bool = False
    daily_drawdown_pct: Decimal = Decimal("0")
    total_drawdown_pct: Decimal = Decimal("0")
    max_daily_drawdown: Decimal | None = None
    max_total_drawdown: Decimal | None = None

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        if self.trading_paused:
            return SafetyResult(
                ok=False,
                reason=f"Trading paused: daily DD {self.daily_drawdown_pct:.2%}, total DD {self.total_drawdown_pct:.2%}",
            )

        if self.max_daily_drawdown is not None and self.daily_drawdown_pct > self.max_daily_drawdown:
            return SafetyResult(
                ok=False,
                reason=f"Daily drawdown limit: {self.daily_drawdown_pct:.2%} > {self.max_daily_drawdown:.2%}",
            )

        if self.max_total_drawdown is not None and self.total_drawdown_pct > self.max_total_drawdown:
            return SafetyResult(
                ok=False,
                reason=f"Total drawdown limit: {self.total_drawdown_pct:.2%} > {self.max_total_drawdown:.2%}",
            )

        return SafetyResult(
            ok=True,
            reason=f"Drawdown OK: daily {self.daily_drawdown_pct:.2%}, total {self.total_drawdown_pct:.2%}",
        )


class SignalDeduplication:
    """Deduplicate signals within the cooldown window.

    Tracks the last signal side per symbol. If the same signal side
    arrives again within the cooldown window, it is filtered out.
    Opposite signals (BUY vs SELL) are never deduplicated against each other.

    This prevents the same signal type from being re-processed repeatedly
    during a strong trend, even after a trade has been executed.

    last_signal is a class-level dict so it survives across instances
    (the orchestrator creates a new SignalDeduplication each iteration).

    last_signal_id is a class-level dict for signal ID-based deduplication.
    """

    # Class-level tracking dicts — shared across all instances
    _last_signal: dict[str, tuple[str, datetime]] = {}
    _last_signal_id: dict[str, datetime] = {}

    def __init__(
        self,
        config: AutomationConfig,
        trade_history: TradeHistory,
        cooldown_check: CooldownCheck | None = None,
    ) -> None:
        self.config = config
        self.trade_history = trade_history
        self.cooldown_check = cooldown_check
        self.min_edge: Decimal | None = None
        # Ensure class-level dicts exist
        if not hasattr(SignalDeduplication, "_last_signal"):
            SignalDeduplication._last_signal = {}
        if not hasattr(SignalDeduplication, "_last_signal_id"):
            SignalDeduplication._last_signal_id = {}
        # Alias to class-level for shared state
        self.last_signal = SignalDeduplication._last_signal

    @classmethod
    def clear_all(cls) -> None:
        """Clear all class-level state. Useful for testing and restart recovery."""
        cls._last_signal.clear()
        cls._last_signal_id.clear()

    @classmethod
    def clear_last_signal(cls) -> None:
        """Alias for clear_all. Maintains backward compatibility."""
        cls.clear_all()

    def check(self, *, intent: OrderIntent) -> SafetyResult:
        symbol_config = self.config.get_symbol_config(intent.symbol)

        if symbol_config.cooldown_seconds <= 0:
            return SafetyResult(ok=True, reason="No cooldown configured")

        last_signal_time = self.trade_history.get_last_trade_time(intent.symbol)

        # If a CooldownCheck reference is provided, use it for cooldown boundary
        if self.cooldown_check is not None:
            return self._check_with_cooldown_check(intent, last_signal_time)

        if last_signal_time is None:
            # No previous trades yet. Set last_time to current time.
            # place_order will record a trade after this signal passes,
            # so the second signal will see last_time >= last_signal_time
            # as a duplicate (same side).
            self.last_signal[intent.symbol] = (intent.side, datetime.now(timezone.utc))
            return SafetyResult(ok=True, reason="No previous trades")

        time_since_last = datetime.now(timezone.utc) - last_signal_time
        cooldown = timedelta(seconds=symbol_config.cooldown_seconds)

        if time_since_last < cooldown:
            remaining = cooldown - time_since_last
            key = intent.symbol

            # Signal ID dedup: check for duplicate signal_id first
            if intent.signal_id is not None:
                sig_key = f"{intent.symbol}:{intent.signal_id}"
                if sig_key in SignalDeduplication._last_signal_id:
                    return SafetyResult(
                        ok=False,
                        reason=f"Signal deduplication: duplicate signal_id '{intent.signal_id}' for {intent.symbol} — {remaining.total_seconds():.0f}s remaining",
                    )
                SignalDeduplication._last_signal_id[sig_key] = datetime.now(timezone.utc)
                # New signal_id — pass through (first occurrence by ID)
                self.last_signal[key] = (intent.side, last_signal_time)
                return SafetyResult(
                    ok=True,
                    reason=f"Signal deduplication: first {intent.side} for {intent.symbol} (new signal_id '{intent.signal_id}') — {remaining.total_seconds():.0f}s remaining",
                )

            if key in self.last_signal:
                last_side, last_time = self.last_signal[key]
                if last_side == intent.side:
                    # Check if this is a first occurrence (time is strictly after trade)
                    # vs. a true duplicate (time is at or before trade, meaning
                    # the first signal already set last_time to the trade's time).
                    if last_time > last_signal_time:
                        # First occurrence — update time to trade's time so
                        # subsequent signals correctly identify as duplicates.
                        self.last_signal[key] = (intent.side, last_signal_time)
                        return SafetyResult(
                            ok=True,
                            reason=f"Signal deduplication: first {intent.side} for {intent.symbol} within cooldown — {remaining.total_seconds():.0f}s remaining",
                        )
                    # Duplicate — reject
                    return SafetyResult(
                        ok=False,
                        reason=f"Signal deduplication: duplicate {intent.side} for {intent.symbol} — {remaining.total_seconds():.0f}s remaining since last {last_side}",
                    )
                # Different side — pass through and update tracking
                self.last_signal[key] = (intent.side, last_signal_time)
                return SafetyResult(
                    ok=True,
                    reason=f"Signal deduplication: {intent.side} for {intent.symbol} (different from last {last_side}) — {remaining.total_seconds():.0f}s remaining",
                )

            # First occurrence within cooldown — record and pass through.
            # The first signal after a trade triggers the trade;
            # subsequent same-side signals are the duplicates.
            self.last_signal[key] = (intent.side, last_signal_time)
            return SafetyResult(
                ok=True,
                reason=f"Signal deduplication: first {intent.side} for {intent.symbol} within cooldown — {remaining.total_seconds():.0f}s remaining",
            )

        # Cooldown has passed — reset the signal tracking for this symbol
        # by clearing the entry. This ensures the next signal enters the
        # "first occurrence" branch. If a new trade has been recorded since
        # the last signal, last_signal_time will be newer and the signal
        # will correctly be treated as a fresh start to a new cooldown cycle.
        self.last_signal.pop(intent.symbol, None)
        return SafetyResult(ok=True, reason="Signal deduplication: cooldown passed")

    def _check_with_cooldown_check(
        self,
        intent: OrderIntent,
        last_signal_time: datetime | None,
    ) -> SafetyResult:
        """Check with a unified CooldownCheck reference."""
        symbol_config = self.config.get_symbol_config(intent.symbol)

        if last_signal_time is None:
            self.last_signal[intent.symbol] = (intent.side, datetime.now(timezone.utc))
            return SafetyResult(ok=True, reason="No previous trades")

        time_since_last = datetime.now(timezone.utc) - last_signal_time
        cooldown = timedelta(seconds=symbol_config.cooldown_seconds)

        if time_since_last < cooldown:
            remaining = cooldown - time_since_last
            key = intent.symbol

            # Signal ID dedup: check for duplicate signal_id first
            if hasattr(intent, "signal_id") and intent.signal_id is not None:
                sig_key = f"{intent.symbol}:{intent.signal_id}"
                if sig_key in SignalDeduplication._last_signal_id:
                    return SafetyResult(
                        ok=False,
                        reason=f"Signal deduplication: duplicate signal_id '{intent.signal_id}' for {intent.symbol} — {remaining.total_seconds():.0f}s remaining",
                    )
                SignalDeduplication._last_signal_id[sig_key] = datetime.now(timezone.utc)

            if key in self.last_signal:
                last_side, last_time = self.last_signal[key]
                if last_side == intent.side:
                    if last_time > last_signal_time:
                        self.last_signal[key] = (intent.side, last_signal_time)
                        return SafetyResult(
                            ok=True,
                            reason=f"Signal deduplication (unified): first {intent.side} for {intent.symbol} within cooldown — {remaining.total_seconds():.0f}s remaining",
                        )
                    return SafetyResult(
                        ok=False,
                        reason=f"Signal deduplication (unified): duplicate {intent.side} for {intent.symbol} — {remaining.total_seconds():.0f}s remaining since last {last_side}",
                    )
                self.last_signal[key] = (intent.side, last_signal_time)
                return SafetyResult(
                    ok=True,
                    reason=f"Signal deduplication (unified): {intent.side} for {intent.symbol} (different from last {last_side}) — {remaining.total_seconds():.0f}s remaining",
                )

            self.last_signal[key] = (intent.side, last_signal_time)
            return SafetyResult(
                ok=True,
                reason=f"Signal deduplication (unified): first {intent.side} for {intent.symbol} within cooldown — {remaining.total_seconds():.0f}s remaining",
            )

        # Cooldown passed
        self.last_signal.pop(intent.symbol, None)
        return SafetyResult(ok=True, reason="Signal deduplication (unified): cooldown passed")
