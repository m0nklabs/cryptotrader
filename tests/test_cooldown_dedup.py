"""Unit tests for cooldown deduplication behavior.

Tests rapid successive signals, cooldown expiration, post-cooldown processing,
and edge cases like overlapping cooldown periods and class-level state management.

Acceptance criteria:
- Suppression during cooldown works correctly
- Normal processing after cooldown expires
- Edge cases: overlapping cooldowns, multi-symbol, rapid signals
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


from core.automation.safety import (
    CooldownCheck,
    SignalDeduplication,
)
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


def _add_trade_at(history: TradeHistory, symbol: str, ts: datetime) -> None:
    """Add a trade record at an exact timestamp."""
    history.add_trade(symbol, ts)


def _set_history_trade_time(history: TradeHistory, symbol: str, seconds_ago: int) -> None:
    """Replace all trades for a symbol with one at the given offset."""
    old = [t for t in history.trades if t.symbol == symbol]
    for t in old:
        history.trades.remove(t)
    history.trades.append(
        TradeRecord(symbol=symbol, timestamp=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago))
    )


# ─── Rapid successive signals ─────────────────────────────────────────────────


class TestRapidSuccessiveSignals:
    """Rapid successive signals should be deduplicated during cooldown."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_five_rapid_same_side_signals(self) -> None:
        """Five BUY signals in quick succession: first passes, four deduplicated."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        results = []
        for _ in range(5):
            r = check.check(intent=intent)
            results.append(r)

        assert results[0].ok is True  # first occurrence
        assert all(r.ok is False for r in results[1:])  # rest deduplicated

    def test_rapid_signals_different_sides(self) -> None:
        """BUY/SELL/BUY in rapid succession: each passes (different side)."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True

        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100")))
        assert r2.ok is True  # different side

        r3 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r3.ok is True  # BUY after SELL is new

        r4 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r4.ok is False  # duplicate BUY

    def test_rapid_mixed_sequence(self) -> None:
        """BUY/BUY/SELL/SELL/BUY sequence: correct dedup pattern."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        # BUY 1 — first occurrence
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True

        # BUY 2 — duplicate
        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is False

        # SELL — different side
        r3 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100")))
        assert r3.ok is True

        # SELL 2 — duplicate
        r4 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100")))
        assert r4.ok is False

        # BUY 3 — new (BUY after SELL)
        r5 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r5.ok is True


# ─── Cooldown expiration ──────────────────────────────────────────────────────


class TestCooldownExpiration:
    """Signals should pass normally after cooldown expires."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_cooldown_expires_allows_new_signal(self) -> None:
        """After cooldown expires, a new signal passes through (not a duplicate)."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        # Simulate trade 70 seconds ago (past 60s cooldown)
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)

        check = SignalDeduplication(config=config, trade_history=history)

        # First signal after cooldown — should pass (not deduplicated)
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True
        assert "passed" in r1.reason.lower()

    def test_cooldown_expires_twice(self) -> None:
        """Two consecutive cooldown cycles: each cycle starts fresh."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        check = SignalDeduplication(config=config, trade_history=history)

        # Cycle 1: trade at T-10, within cooldown
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=10)

        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True  # first in cycle

        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is False  # duplicate in cycle

        # Advance time past cooldown
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)

        r3 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r3.ok is True  # cooldown passed, fresh start

        r4 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r4.ok is True  # after reset, next signal is first occurrence

        # Now a trade happens again
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=10)

        r5 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r5.ok is True  # first of new cycle

        r6 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r6.ok is False  # duplicate in new cycle


# ─── Post-cooldown processing ─────────────────────────────────────────────────


class TestPostCooldownProcessing:
    """After cooldown, signals should be processed normally."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_post_cooldown_first_occurrence(self) -> None:
        """After cooldown, the first signal is treated as first occurrence."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        # Cooldown passed (trade 70s ago)
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)

        check = SignalDeduplication(config=config, trade_history=history)

        # Signal passes through as first occurrence
        r = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r.ok is True
        assert "cooldown passed" in r.reason.lower()

    def test_post_cooldown_next_signal_is_first(self) -> None:
        """After cooldown reset, the immediately following signal is also first occurrence."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)

        check = SignalDeduplication(config=config, trade_history=history)

        # First signal triggers cooldown reset
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True

        # Second signal — because last_signal was popped, this enters first-occurrence branch
        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is True

    def test_post_cooldown_new_trade_starts_new_cycle(self) -> None:
        """A new trade after cooldown starts a fresh cooldown cycle."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        # First: cooldown passed
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)

        check = SignalDeduplication(config=config, trade_history=history)

        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True

        # New trade recorded (simulating post-cooldown trade execution)
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=10)

        # Signal should now be in a new cooldown cycle
        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is True  # first of new cycle

        r3 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r3.ok is False  # duplicate in new cycle


# ─── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: overlapping cooldowns, multi-symbol, class-level state."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_overlapping_cooldown_periods(self) -> None:
        """Two symbols with different cooldowns overlap correctly."""
        btc_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=300)
        eth_config = SymbolConfig(symbol="ETH/USDT", cooldown_seconds=60)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": btc_config, "ETH/USDT": eth_config})
        history = TradeHistory()

        # BTC: trade 100s ago (within 300s cooldown)
        # ETH: trade 70s ago (past 60s cooldown)
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=100)
        _set_history_trade_time(history, "ETH/USDT", seconds_ago=70)

        check = SignalDeduplication(config=config, trade_history=history)

        # BTC: within cooldown — first occurrence
        r_btc = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_btc.ok is True

        # ETH: cooldown passed — should pass through
        r_eth = check.check(
            intent=OrderIntent(exchange="binance", symbol="ETH/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_eth.ok is True

        # Second BTC: still within cooldown — duplicate
        r_btc2 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_btc2.ok is False

        # Second ETH: cooldown already passed, still passes
        r_eth2 = check.check(
            intent=OrderIntent(exchange="binance", symbol="ETH/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_eth2.ok is True

    def test_class_level_state_sharing(self) -> None:
        """Multiple SignalDeduplication instances share class-level state."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        # First instance sets state
        check1 = SignalDeduplication(config=config, trade_history=history)
        r1 = check1.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True

        # Second instance sees the state from first instance
        check2 = SignalDeduplication(config=config, trade_history=history)
        r2 = check2.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is False  # deduplicated by first instance's state

    def test_clear_all_isolates_state(self) -> None:
        """clear_all resets state so new signals start fresh."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        # Set up state
        check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))

        # Verify state exists
        assert "BTC/USDT" in SignalDeduplication._last_signal

        # Clear all
        SignalDeduplication.clear_all()

        # State is reset
        assert len(SignalDeduplication._last_signal) == 0
        assert len(SignalDeduplication._last_signal_id) == 0

        # New signal passes as first occurrence
        r = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r.ok is True

    def test_class_level_state_survives_instance_recreation(self) -> None:
        """Class-level state persists across SignalDeduplication instance creation/destruction."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        # Create instance, set state
        check1 = SignalDeduplication(config=config, trade_history=history)
        check1.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))

        # Delete instance — state should persist (class-level, not instance-level)
        del check1

        # Create new instance — should see old state
        check2 = SignalDeduplication(config=config, trade_history=history)
        r = check2.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r.ok is False  # deduplicated against check1's state

    def test_zero_cooldown_no_dedup(self) -> None:
        """Zero cooldown_seconds means no deduplication at all."""
        config = _make_config(cooldown_seconds=0)
        history = TradeHistory()
        check = SignalDeduplication(config=config, trade_history=history)

        # Multiple same-side signals all pass
        for _ in range(5):
            r = check.check(
                intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
            )
            assert r.ok is True

    def test_unified_cooldown_check_integration(self) -> None:
        """SignalDeduplication with CooldownCheck uses unified cooldown tracking."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=30)

        cooldown_check = CooldownCheck(config=config, trade_history=history)
        check = SignalDeduplication(
            config=config,
            trade_history=history,
            cooldown_check=cooldown_check,
        )

        # Cooldown active — dedup runs
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True

        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is False

        # CooldownCheck says active, so dedup should work
        cooldown_active = cooldown_check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert cooldown_active.ok is False

    def test_unified_cooldown_expiry(self) -> None:
        """Unified cooldown: when CooldownCheck passes, SignalDeduplication resets."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)  # past cooldown

        cooldown_check = CooldownCheck(config=config, trade_history=history)
        check = SignalDeduplication(
            config=config,
            trade_history=history,
            cooldown_check=cooldown_check,
        )

        # Cooldown passed — should pass through
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True
        assert "unified" in r1.reason.lower()

    def test_no_previous_trades_with_cooldown_check(self) -> None:
        """No previous trades: sets last_signal to current time."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()  # empty

        cooldown_check = CooldownCheck(config=config, trade_history=history)
        check = SignalDeduplication(
            config=config,
            trade_history=history,
            cooldown_check=cooldown_check,
        )

        # First signal — no previous trades, sets last_signal
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True
        assert "No previous trades" in r1.reason

        # Verify last_signal was set
        assert "BTC/USDT" in SignalDeduplication._last_signal

    def test_signal_id_dedup_during_cooldown(self) -> None:
        """Duplicate signal IDs are filtered even within cooldown."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        # Same signal ID — deduplicated
        r1 = check.check(
            intent=OrderIntent(
                exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"), signal_id="abc"
            )
        )
        assert r1.ok is True  # first occurrence

        r2 = check.check(
            intent=OrderIntent(
                exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"), signal_id="abc"
            )
        )
        assert r2.ok is False  # duplicate ID

        r3 = check.check(
            intent=OrderIntent(
                exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"), signal_id="def"
            )
        )
        assert r3.ok is True  # different ID

    def test_signal_id_dedup_crosses_side(self) -> None:
        """Signal ID dedup works across different sides."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        # BUY with ID
        r1 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"), signal_id="x")
        )
        assert r1.ok is True

        # SELL with same ID — still deduplicated (ID is tracked per symbol, not per side)
        r2 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100"), signal_id="x")
        )
        assert r2.ok is False  # duplicate ID

        # BUY with different ID
        r3 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"), signal_id="y")
        )
        assert r3.ok is True

    def test_no_signal_id_no_dedup(self) -> None:
        """Signals without signal_id are deduplicated by side only."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)

        # First BUY — passes
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True

        # Second BUY (no ID) — deduplicated by side
        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is False

    def test_min_edge_filter(self) -> None:
        """min_edge threshold affects signal passing."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)

        check = SignalDeduplication(config=config, trade_history=history)
        check.min_edge = Decimal("0.001")  # 0.1%

        # Signal with sufficient edge passes
        r = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r.ok is True

    def test_multiple_symbols_independent_dedup(self) -> None:
        """Different symbols maintain independent dedup state."""
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

        # BTC first — passes
        r_btc1 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_btc1.ok is True

        # ETH first — passes (independent)
        r_eth1 = check.check(
            intent=OrderIntent(exchange="binance", symbol="ETH/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_eth1.ok is True

        # BTC second — duplicate
        r_btc2 = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_btc2.ok is False

        # ETH second — duplicate (independent)
        r_eth2 = check.check(
            intent=OrderIntent(exchange="binance", symbol="ETH/USDT", side="BUY", amount=Decimal("100"))
        )
        assert r_eth2.ok is False


# ─── CooldownCheck vs SignalDeduplication gap ─────────────────────────────────


class TestCooldownGap:
    """Tests for the gap between CooldownCheck and SignalDeduplication tracking."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_cooldown_check_and_dedup_independent_without_link(self) -> None:
        """Without CooldownCheck reference, they track independently."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=30)

        # No CooldownCheck reference
        check = SignalDeduplication(config=config, trade_history=history)

        # CooldownCheck would say active (30s < 120s)
        cc = CooldownCheck(config=config, trade_history=history)
        cc_result = cc.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert cc_result.ok is False  # cooldown active

        # SignalDeduplication uses its own time check
        # Since last_signal_time is 30s ago and cooldown is 120s, it's within cooldown
        sd_result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert sd_result.ok is True  # first occurrence

    def test_cooldown_check_and_dedup_unified(self) -> None:
        """With CooldownCheck reference, dedup defers to it for cooldown boundary."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)  # past cooldown

        cooldown_check = CooldownCheck(config=config, trade_history=history)
        check = SignalDeduplication(
            config=config,
            trade_history=history,
            cooldown_check=cooldown_check,
        )

        # CooldownCheck says passed (70s > 60s)
        cc_result = cooldown_check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert cc_result.ok is True

        # SignalDeduplication should also say passed
        sd_result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert sd_result.ok is True
        assert "unified" in sd_result.reason.lower()

    def test_cooldown_check_and_dedup_both_active(self) -> None:
        """Both CooldownCheck and SignalDeduplication active simultaneously."""
        config = _make_config(cooldown_seconds=120)
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=30)

        cooldown_check = CooldownCheck(config=config, trade_history=history)
        check = SignalDeduplication(
            config=config,
            trade_history=history,
            cooldown_check=cooldown_check,
        )

        # Both should agree: cooldown active
        cc = cooldown_check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert cc.ok is False  # cooldown active

        # SignalDeduplication within cooldown — first occurrence
        sd = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert sd.ok is True

        # Second signal: both should say deduplicated
        sd2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert sd2.ok is False


# ─── Integration tests ────────────────────────────────────────────────────────


class TestIntegration:
    """End-to-end integration tests combining all dedup scenarios."""

    def setup_method(self) -> None:
        SignalDeduplication.clear_all()

    def test_full_lifecycle(self) -> None:
        """Full lifecycle: no trades → first signal → duplicates → cooldown expires → new cycle."""
        config = _make_config(cooldown_seconds=60)
        history = TradeHistory()

        check = SignalDeduplication(config=config, trade_history=history)

        # Phase 1: No previous trades
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True
        assert "No previous" in r1.reason

        # Phase 2: Record a trade, enter cooldown
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=10)

        # Phase 3: First signal in cooldown — passes
        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is True

        # Phase 4: Duplicate signals — rejected
        r3 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r3.ok is False

        r4 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r4.ok is False

        # Phase 5: SELL passes through
        r5 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100")))
        assert r5.ok is True

        # Phase 6: Cooldown expires
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=70)

        r6 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r6.ok is True
        assert "passed" in r6.reason.lower()

        # Phase 7: New cycle starts
        _set_history_trade_time(history, "BTC/USDT", seconds_ago=10)

        r7 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r7.ok is True  # first of new cycle

        r8 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r8.ok is False  # duplicate in new cycle

    def test_rapid_multi_symbol_lifecycle(self) -> None:
        """Multiple symbols with rapid signals in parallel."""
        btc_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=60)
        eth_config = SymbolConfig(symbol="ETH/USDT", cooldown_seconds=30)
        config = AutomationConfig(
            enabled=True,
            symbol_configs={"BTC/USDT": btc_config, "ETH/USDT": eth_config},
        )
        history = TradeHistory()
        _add_trade(history, "BTC/USDT", seconds_ago=10)
        _add_trade(history, "ETH/USDT", seconds_ago=5)

        check = SignalDeduplication(config=config, trade_history=history)

        # Rapid signals across both symbols
        results = []
        for _ in range(3):
            r_btc = check.check(
                intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
            )
            r_eth = check.check(
                intent=OrderIntent(exchange="binance", symbol="ETH/USDT", side="BUY", amount=Decimal("100"))
            )
            results.append((r_btc, r_eth))

        # BTC: first passes, rest duplicate (60s cooldown)
        assert results[0][0].ok is True  # BTC first
        assert results[1][0].ok is False  # BTC dup
        assert results[2][0].ok is False  # BTC dup

        # ETH: first passes, rest duplicate (30s cooldown)
        assert results[0][1].ok is True  # ETH first
        assert results[1][1].ok is False  # ETH dup
        assert results[2][1].ok is False  # ETH dup
