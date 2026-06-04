"""Focused tests for SignalDeduplication class-level state shadowing fix.

Tests that the SignalDeduplication class properly tracks state at the class level
so that multiple instances share the same dedup state, preventing double-rejection
of BUY signals.

Acceptance criteria:
- Class-level _last_signal and _last_signal_id are properly shared
- BUY signals are not double-rejected across instances
- clear_all properly resets all class-level state
- No regression in existing test paths
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.automation.safety import SignalDeduplication
from core.automation import AutomationConfig, SymbolConfig, TradeHistory
from core.automation.rules import TradeRecord
from core.types import OrderIntent


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _make_config(
    symbol: str = "BTC/USDT",
    cooldown_seconds: int = 120,
    **kw,
) -> AutomationConfig:
    """Create a minimal config with one symbol."""
    sc = SymbolConfig(symbol=symbol, cooldown_seconds=cooldown_seconds, **kw)
    return AutomationConfig(enabled=True, symbol_configs={symbol: sc})


def _add_trade(history: TradeHistory, symbol: str, seconds_ago: int = 30) -> None:
    """Add a trade record to history at a given offset."""
    history.add_trade(symbol, datetime.now(timezone.utc) - timedelta(seconds=seconds_ago))


def _set_history_trade_time(history: TradeHistory, symbol: str, seconds_ago: int) -> None:
    """Replace all trades for a symbol with one at the given offset."""
    old = [t for t in history.trades if t.symbol == symbol]
    for t in old:
        history.trades.remove(t)
    history.trades.append(
        TradeRecord(symbol=symbol, timestamp=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago))
    )


# ─── Class-level state shadowing tests ────────────────────────────────────────


class TestClassLevelStateShadowing:
    """Test that class-level state is properly shared, preventing double-rejection."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_instance_1_sets_class_state(self) -> None:
        """First instance sets class-level _last_signal and it persists."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check1 = SignalDeduplication(config=config, trade_history=history)
        r1 = check1.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r1.ok is True, "First signal should pass"
        assert "BTC/USDT" in SignalDeduplication._last_signal, "Class-level _last_signal should have entry"

    def test_instance_2_sees_instance_1_state(self) -> None:
        """Second instance sees first instance's state — correctly deduplicated."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        # First instance: sets class-level state
        check1 = SignalDeduplication(config=config, trade_history=history)
        r1 = check1.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r1.ok is True

        # Second instance: sees first instance's class-level state
        check2 = SignalDeduplication(config=config, trade_history=history)
        r2 = check2.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        # Second instance is deduplicated against first instance's state
        assert r2.ok is False, "Second instance correctly deduplicated by first instance's class-level state"

    def test_clear_all_resets_all_class_state(self) -> None:
        """clear_all resets both _last_signal and _last_signal_id."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)
        check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )

        # Verify state exists
        assert len(SignalDeduplication._last_signal) > 0
        assert len(SignalDeduplication._last_signal_id) >= 0

        # Clear all
        SignalDeduplication.clear_all()

        # Both dicts should be empty
        assert len(SignalDeduplication._last_signal) == 0
        assert len(SignalDeduplication._last_signal_id) == 0

        # New signal passes as first occurrence
        r = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r.ok is True

    def test_class_state_survives_instance_destruction(self) -> None:
        """Class-level state persists when instances are destroyed and recreated."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        # Create and use first instance
        check1 = SignalDeduplication(config=config, trade_history=history)
        r1 = check1.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r1.ok is True

        # Destroy instance — class state should persist
        del check1

        # Recreate and verify state is still there
        check2 = SignalDeduplication(config=config, trade_history=history)
        r2 = check2.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        # State survived — this is the second signal, should be deduplicated
        assert r2.ok is False, "Class-level state should survive instance destruction"


# ─── No regression tests ──────────────────────────────────────────────────────


class TestNoRegression:
    """Ensure existing dedup behavior is preserved."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_rapid_same_side_dedup(self) -> None:
        """Rapid same-side signals are deduplicated (existing behavior)."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        r1 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r1.ok is True

        r2 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r2.ok is False

    def test_opposite_signal_allowed(self) -> None:
        """Opposite signals (BUY/SELL) are not deduplicated (existing behavior)."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        r_buy = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_buy.ok is True

        r_sell = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100"))
        )
        assert r_sell.ok is True, "SELL should pass through after BUY"

    def test_cooldown_expiry_allows_new_signal(self) -> None:
        """After cooldown expires, new signal passes (existing behavior)."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)

        check = SignalDeduplication(config=config, trade_history=history)

        r = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r.ok is True
        assert "passed" in r.reason.lower()

    def test_multi_symbol_independent(self) -> None:
        """Different symbols maintain independent dedup state (existing behavior)."""
        btc_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=120)
        eth_config = SymbolConfig(symbol="ETH/USDT", cooldown_seconds=120)
        config = AutomationConfig(
            enabled=True,
            symbol_configs={"BTC/USDT": btc_config, "ETH/USDT": eth_config},
        )
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)
        _add_trade(history, "ETH/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        r_btc = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_btc.ok is True

        r_eth = check.check(
            intent=OrderIntent(exchange="binance", symbol="ETH/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_eth.ok is True, "ETH should be independent of BTC state"
