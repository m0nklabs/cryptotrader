"""Tests for automation engine skeleton."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.automation import (
    AuditEvent,
    AuditLogger,
    AutomationConfig,
    BalanceCheck,
    CooldownCheck,
    DailyLossCheck,
    DailyTradeCountCheck,
    KillSwitchCheck,
    PositionSizeCheck,
    SlippageCheck,
    SymbolConfig,
    TradeHistory,
    run_safety_checks,
)
from core.types import OrderIntent


# ========== Rules Tests ==========


class TestAutomationConfig:
    """Tests for AutomationConfig."""

    def test_default_config_disabled(self) -> None:
        """Test that automation is disabled by default."""
        config = AutomationConfig()
        assert config.enabled is False

    def test_global_enable_disable(self) -> None:
        """Test global enable/disable functionality."""
        config = AutomationConfig(enabled=True)
        assert config.enabled is True
        assert config.is_symbol_enabled("BTC/USDT") is True

        config = AutomationConfig(enabled=False)
        assert config.enabled is False
        assert config.is_symbol_enabled("BTC/USDT") is False

    def test_symbol_config_enable_disable(self) -> None:
        """Test per-symbol enable/disable."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", enabled=False)
        config = AutomationConfig(
            enabled=True,
            symbol_configs={"BTC/USDT": symbol_config},
        )

        assert config.is_symbol_enabled("BTC/USDT") is False
        assert config.is_symbol_enabled("ETH/USDT") is True  # Other symbols enabled by default

    def test_get_symbol_config_default(self) -> None:
        """Test getting default config for unconfigured symbol."""
        config = AutomationConfig(
            max_position_size_default=Decimal("1000"),
            max_slippage_bps_default=25,
            cooldown_seconds_default=120,
        )

        symbol_config = config.get_symbol_config("BTC/USDT")
        assert symbol_config.symbol == "BTC/USDT"
        assert symbol_config.enabled is True
        assert symbol_config.max_position_size == Decimal("1000")
        assert symbol_config.max_slippage_bps == 25
        assert symbol_config.cooldown_seconds == 120

    def test_get_symbol_config_custom(self) -> None:
        """Test getting custom config for configured symbol."""
        btc_config = SymbolConfig(
            symbol="BTC/USDT",
            max_position_size=Decimal("5000"),
            max_daily_trades=10,
            cooldown_seconds=300,
        )
        config = AutomationConfig(
            enabled=True,
            symbol_configs={"BTC/USDT": btc_config},
        )

        symbol_config = config.get_symbol_config("BTC/USDT")
        assert symbol_config.max_position_size == Decimal("5000")
        assert symbol_config.max_daily_trades == 10
        assert symbol_config.cooldown_seconds == 300


class TestTradeHistory:
    """Tests for TradeHistory."""

    def test_add_trade(self) -> None:
        """Test adding trades to history."""
        history = TradeHistory()
        now = datetime.now(timezone.utc)

        history.add_trade("BTC/USDT", now)
        assert len(history.trades) == 1
        assert history.trades[0].symbol == "BTC/USDT"
        assert history.trades[0].timestamp == now

    def test_get_trades_since(self) -> None:
        """Test getting trades since a specific time."""
        history = TradeHistory()
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        two_hours_ago = now - timedelta(hours=2)

        history.add_trade("BTC/USDT", two_hours_ago)
        history.add_trade("ETH/USDT", hour_ago)
        history.add_trade("BTC/USDT", now)

        recent_trades = history.get_trades_since(hour_ago)
        assert len(recent_trades) == 2
        assert all(t.timestamp >= hour_ago for t in recent_trades)

    def test_get_symbol_trades_since(self) -> None:
        """Test getting symbol-specific trades."""
        history = TradeHistory()
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)

        history.add_trade("BTC/USDT", hour_ago)
        history.add_trade("ETH/USDT", hour_ago)
        history.add_trade("BTC/USDT", now)

        btc_trades = history.get_symbol_trades_since("BTC/USDT", hour_ago)
        assert len(btc_trades) == 2
        assert all(t.symbol == "BTC/USDT" for t in btc_trades)

    def test_get_last_trade_time(self) -> None:
        """Test getting last trade time for a symbol."""
        history = TradeHistory()
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)

        assert history.get_last_trade_time("BTC/USDT") is None

        history.add_trade("BTC/USDT", hour_ago)
        history.add_trade("BTC/USDT", now)

        last_time = history.get_last_trade_time("BTC/USDT")
        assert last_time == now

    def test_get_daily_trade_count(self) -> None:
        """Test getting daily trade count."""
        history = TradeHistory()
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        history.add_trade("BTC/USDT", yesterday)
        history.add_trade("BTC/USDT", now)
        history.add_trade("ETH/USDT", now)

        # Global count (only today's trades)
        assert history.get_daily_trade_count() == 2

        # Symbol-specific count
        assert history.get_daily_trade_count("BTC/USDT") == 1
        assert history.get_daily_trade_count("ETH/USDT") == 1


# ========== Safety Check Tests ==========


class TestKillSwitchCheck:
    """Tests for KillSwitchCheck."""

    def test_global_disabled(self) -> None:
        """Test kill switch when globally disabled."""
        config = AutomationConfig(enabled=False)
        check = KillSwitchCheck(config=config)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "globally disabled" in result.reason

    def test_global_enabled(self) -> None:
        """Test kill switch when globally enabled."""
        config = AutomationConfig(enabled=True)
        check = KillSwitchCheck(config=config)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_symbol_disabled(self) -> None:
        """Test kill switch when symbol is disabled."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", enabled=False)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        check = KillSwitchCheck(config=config)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "disabled for BTC/USDT" in result.reason


class TestPositionSizeCheck:
    """Tests for PositionSizeCheck."""

    def test_no_limit(self) -> None:
        """Test when no position limit is set."""
        config = AutomationConfig(enabled=True)
        check = PositionSizeCheck(config=config)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("10000"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_within_limit(self) -> None:
        """Test position size within limit."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", max_position_size=Decimal("5000"))
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        check = PositionSizeCheck(config=config, current_position_value=Decimal("2000"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("2000"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_exceeds_limit(self) -> None:
        """Test position size exceeds limit."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", max_position_size=Decimal("5000"))
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        check = PositionSizeCheck(config=config, current_position_value=Decimal("3000"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("3000"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "limit exceeded" in result.reason

    def test_sell_order_reduces_position(self) -> None:
        """Test that SELL orders reduce position size."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", max_position_size=Decimal("5000"))
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        check = PositionSizeCheck(config=config, current_position_value=Decimal("4000"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("2000"))

        result = check.check(intent=intent)
        assert result.ok is True  # 4000 - 2000 = 2000, which is within the 5000 limit


class TestCooldownCheck:
    """Tests for CooldownCheck."""

    def test_no_cooldown(self) -> None:
        """Test when no cooldown is configured."""
        config = AutomationConfig(enabled=True, cooldown_seconds_default=0)
        history = TradeHistory()
        check = CooldownCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_no_previous_trades(self) -> None:
        """Test when there are no previous trades."""
        config = AutomationConfig(enabled=True, cooldown_seconds_default=60)
        history = TradeHistory()
        check = CooldownCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_cooldown_active(self) -> None:
        """Test when cooldown is still active."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=120)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)  # 30 seconds ago
        history.add_trade("BTC/USDT", recent_time)

        check = CooldownCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "Cooldown active" in result.reason

    def test_cooldown_passed(self) -> None:
        """Test when cooldown has passed."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=60)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)  # 2 minutes ago
        history.add_trade("BTC/USDT", old_time)

        check = CooldownCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True


class TestDailyTradeCountCheck:
    """Tests for DailyTradeCountCheck."""

    def test_no_limit(self) -> None:
        """Test when no limit is set."""
        config = AutomationConfig(enabled=True)
        history = TradeHistory()
        check = DailyTradeCountCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_symbol_limit_not_exceeded(self) -> None:
        """Test symbol limit not exceeded."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", max_daily_trades=5)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        now = datetime.now(timezone.utc)
        for _ in range(3):
            history.add_trade("BTC/USDT", now)

        check = DailyTradeCountCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_symbol_limit_exceeded(self) -> None:
        """Test symbol limit exceeded."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", max_daily_trades=3)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        now = datetime.now(timezone.utc)
        for _ in range(3):
            history.add_trade("BTC/USDT", now)

        check = DailyTradeCountCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "Daily trade limit" in result.reason

    def test_global_limit_exceeded(self) -> None:
        """Test global limit exceeded."""
        config = AutomationConfig(enabled=True, max_daily_trades_global=5)
        history = TradeHistory()
        now = datetime.now(timezone.utc)
        for i in range(5):
            history.add_trade(f"SYM{i}", now)

        check = DailyTradeCountCheck(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "Global daily trade limit" in result.reason


class TestBalanceCheck:
    """Tests for BalanceCheck."""

    def test_no_minimum_required(self) -> None:
        """Test when no minimum balance is required."""
        config = AutomationConfig(enabled=True)
        check = BalanceCheck(config=config, current_balance=Decimal("100"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("50"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_sufficient_balance(self) -> None:
        """Test with sufficient balance."""
        config = AutomationConfig(enabled=True, min_balance_required=Decimal("100"))
        check = BalanceCheck(config=config, current_balance=Decimal("500"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("200"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_below_minimum_balance(self) -> None:
        """Test when balance is below minimum."""
        config = AutomationConfig(enabled=True, min_balance_required=Decimal("1000"))
        check = BalanceCheck(config=config, current_balance=Decimal("500"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "Insufficient balance" in result.reason

    def test_insufficient_for_order(self) -> None:
        """Test when balance is insufficient for the order."""
        config = AutomationConfig(enabled=True, min_balance_required=Decimal("100"))
        check = BalanceCheck(config=config, current_balance=Decimal("500"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("600"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "Insufficient balance for order" in result.reason


class TestDailyLossCheck:
    """Tests for DailyLossCheck."""

    def test_no_limit(self) -> None:
        """Test when no loss limit is set."""
        config = AutomationConfig(enabled=True)
        check = DailyLossCheck(config=config, daily_pnl=Decimal("-500"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_within_loss_limit(self) -> None:
        """Test when loss is within limit."""
        config = AutomationConfig(enabled=True, max_daily_loss=Decimal("1000"))
        check = DailyLossCheck(config=config, daily_pnl=Decimal("-500"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_exceeds_loss_limit(self) -> None:
        """Test when loss exceeds limit."""
        config = AutomationConfig(enabled=True, max_daily_loss=Decimal("500"))
        check = DailyLossCheck(config=config, daily_pnl=Decimal("-600"))
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "Daily loss limit exceeded" in result.reason


class TestSlippageCheck:
    """Tests for SlippageCheck."""

    def test_no_limit(self) -> None:
        """Test when no slippage limit is set."""
        config = AutomationConfig(enabled=True)
        check = SlippageCheck(config=config, expected_slippage_bps=100)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_within_limit(self) -> None:
        """Test when slippage is within limit."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", max_slippage_bps=50)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        check = SlippageCheck(config=config, expected_slippage_bps=30)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True

    def test_exceeds_limit(self) -> None:
        """Test when slippage exceeds limit."""
        symbol_config = SymbolConfig(symbol="BTC/USDT", max_slippage_bps=50)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        check = SlippageCheck(config=config, expected_slippage_bps=75)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is False
        assert "slippage too high" in result.reason


class TestRunSafetyChecks:
    """Tests for run_safety_checks function."""

    def test_all_checks_pass(self) -> None:
        """Test when all checks pass."""
        config = AutomationConfig(enabled=True)
        checks = [
            KillSwitchCheck(config=config),
            BalanceCheck(config=config, current_balance=Decimal("1000")),
        ]
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = run_safety_checks(checks=checks, intent=intent)
        assert result.ok is True

    def test_first_check_fails(self) -> None:
        """Test when first check fails."""
        config = AutomationConfig(enabled=False)  # Kill switch disabled
        checks = [
            KillSwitchCheck(config=config),
            BalanceCheck(config=config, current_balance=Decimal("1000")),
        ]
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = run_safety_checks(checks=checks, intent=intent)
        assert result.ok is False
        assert "globally disabled" in result.reason

    def test_later_check_fails(self) -> None:
        """Test when a later check fails."""
        config = AutomationConfig(enabled=True, min_balance_required=Decimal("1000"))
        checks = [
            KillSwitchCheck(config=config),
            BalanceCheck(config=config, current_balance=Decimal("50")),
        ]
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = run_safety_checks(checks=checks, intent=intent)
        assert result.ok is False
        assert "Insufficient balance" in result.reason


# ========== Audit Tests ==========


class TestAuditEvent:
    """Tests for AuditEvent."""

    def test_to_dict(self) -> None:
        """Test converting event to dictionary."""
        now = datetime.now(timezone.utc)
        event = AuditEvent(
            event_type="decision",
            message="Test message",
            timestamp=now,
            severity="info",
            context={"key": "value"},
        )

        result = event.to_dict()
        assert result["event_type"] == "decision"
        assert result["message"] == "Test message"
        assert result["timestamp"] == now.isoformat()
        assert result["severity"] == "info"
        assert result["context"] == {"key": "value"}

    def test_from_dict(self) -> None:
        """Test creating event from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "event_type": "decision",
            "message": "Test message",
            "timestamp": now.isoformat(),
            "severity": "warning",
            "context": {"symbol": "BTC/USDT"},
        }

        event = AuditEvent.from_dict(data)
        assert event.event_type == "decision"
        assert event.message == "Test message"
        assert event.timestamp == now
        assert event.severity == "warning"
        assert event.context == {"symbol": "BTC/USDT"}

    def test_from_dict_with_z_suffix(self) -> None:
        """Test creating event from dictionary with Z suffix timestamp."""
        data = {
            "event_type": "decision",
            "message": "Test message",
            "timestamp": "2024-01-01T12:00:00Z",
            "severity": "info",
            "context": {},
        }

        event = AuditEvent.from_dict(data)
        assert event.event_type == "decision"
        assert event.timestamp.tzinfo is not None  # Should be timezone-aware

    def test_from_dict_invalid_timestamp(self) -> None:
        """Test creating event from dictionary with invalid timestamp."""
        data = {
            "event_type": "error",
            "message": "Test message",
            "timestamp": "invalid-timestamp",
            "severity": "error",
            "context": {},
        }

        # Should not raise an error, just use default timestamp
        event = AuditEvent.from_dict(data)
        assert event.event_type == "error"
        assert event.timestamp is not None  # Should have a default timestamp


class TestAuditLogger:
    """Tests for AuditLogger."""

    def test_log_decision(self) -> None:
        """Test logging a decision."""
        logger = AuditLogger()
        logger.log_decision("allow", "Test reason", "BTC/USDT", {"extra": "data"})

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "decision"
        assert event.context["decision"] == "allow"
        assert event.context["symbol"] == "BTC/USDT"
        assert event.context["extra"] == "data"

    def test_log_safety_check_pass(self) -> None:
        """Test logging a passing safety check."""
        logger = AuditLogger()
        logger.log_safety_check("KillSwitch", True, "All good", "BTC/USDT")

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "safety_check"
        assert event.severity == "info"
        assert event.context["passed"] is True

    def test_log_safety_check_fail(self) -> None:
        """Test logging a failing safety check."""
        logger = AuditLogger()
        logger.log_safety_check("BalanceCheck", False, "Insufficient funds", "BTC/USDT")

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "safety_check"
        assert event.severity == "warning"
        assert event.context["passed"] is False

    def test_log_rule_violation(self) -> None:
        """Test logging a rule violation."""
        logger = AuditLogger()
        logger.log_rule_violation("MaxPositionSize", "Limit exceeded", "BTC/USDT")

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "rule_violation"
        assert event.severity == "warning"

    def test_log_trade_executed(self) -> None:
        """Test logging trade execution."""
        logger = AuditLogger()
        logger.log_trade_executed("BTC/USDT", "BUY", "100", {"dry_run": True})

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "trade_executed"
        assert event.context["symbol"] == "BTC/USDT"
        assert event.context["side"] == "BUY"

    def test_log_trade_rejected(self) -> None:
        """Test logging trade rejection."""
        logger = AuditLogger()
        logger.log_trade_rejected("BTC/USDT", "Failed safety check")

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "trade_rejected"
        assert event.severity == "warning"

    def test_log_kill_switch(self) -> None:
        """Test logging kill switch activation."""
        logger = AuditLogger()
        logger.log_kill_switch("Manual shutdown")

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "kill_switch"
        assert event.severity == "error"

    def test_log_error(self) -> None:
        """Test logging an error."""
        logger = AuditLogger()
        logger.log_error("Something went wrong", {"trace": "error_trace"})

        assert len(logger.events) == 1
        event = logger.events[0]
        assert event.event_type == "error"
        assert event.severity == "error"

    def test_get_events_filter_by_type(self) -> None:
        """Test filtering events by type."""
        logger = AuditLogger()
        logger.log_decision("allow", "Test", "BTC/USDT")
        logger.log_error("Error occurred")
        logger.log_decision("deny", "Test2", "ETH/USDT")

        decisions = logger.get_events(event_type="decision")
        assert len(decisions) == 2
        assert all(e.event_type == "decision" for e in decisions)

    def test_get_events_filter_by_severity(self) -> None:
        """Test filtering events by severity."""
        logger = AuditLogger()
        logger.log_decision("allow", "Test", "BTC/USDT")  # info
        logger.log_error("Error occurred")  # error
        logger.log_kill_switch("Shutdown")  # error

        errors = logger.get_events(severity="error")
        assert len(errors) == 2

    def test_get_events_filter_by_symbol(self) -> None:
        """Test filtering events by symbol."""
        logger = AuditLogger()
        logger.log_decision("allow", "Test", "BTC/USDT")
        logger.log_decision("deny", "Test2", "ETH/USDT")
        logger.log_safety_check("Balance", True, "OK", "BTC/USDT")

        btc_events = logger.get_events(symbol="BTC/USDT")
        assert len(btc_events) == 2
        assert all(e.context.get("symbol") == "BTC/USDT" for e in btc_events)

    def test_clear(self) -> None:
        """Test clearing all events."""
        logger = AuditLogger()
        logger.log_decision("allow", "Test", "BTC/USDT")
        logger.log_error("Error")

        assert len(logger.events) == 2

        logger.clear()
        assert len(logger.events) == 0

    def test_to_json_list(self) -> None:
        """Test exporting events as JSON list."""
        logger = AuditLogger()
        logger.log_decision("allow", "Test", "BTC/USDT")
        logger.log_error("Error occurred")

        json_list = logger.to_json_list()
        assert len(json_list) == 2
        assert all(isinstance(item, dict) for item in json_list)
        assert all("timestamp" in item for item in json_list)
        assert all(isinstance(item["timestamp"], str) for item in json_list)
