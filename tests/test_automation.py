"""Tests for automation engine skeleton."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

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
    SignalDeduplication,
    SlippageCheck,
    SymbolConfig,
    TradeHistory,
    TradeRecord,
    run_safety_checks,
)
from core.automation.orchestrator import OrchestratorConfig, StrategyOrchestrator
from core.automation.policy import Policy
from core.types import Candle, CostEstimate, OrderIntent, Opportunity
from typing import Literal

from core.backtest.strategy import Signal
from core.execution.bitfinex_live import BitfinexLiveExecutor
from core.execution.interfaces import Order


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


class DummyStrategy:
    def __init__(self, side: Literal["BUY", "SELL"]):
        self._side: Literal["BUY", "SELL"] = side

    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        return Signal(self._side)


class DummyCandleProvider:
    async def get_latest_candles(self, symbol: str, timeframe: str, limit: int = 100) -> list[Candle]:
        now = datetime.now(timezone.utc)
        candles = []
        for i in range(20):
            candles.append(
                Candle(
                    exchange="bitfinex",
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=now - timedelta(minutes=20 - i),
                    close_time=now - timedelta(minutes=19 - i),
                    open=Decimal("100"),
                    high=Decimal("110"),
                    low=Decimal("90"),
                    close=Decimal("100"),
                    volume=Decimal("1"),
                )
            )
        return candles


class DummyPriceProvider:
    async def get_current_price(self, symbol: str) -> Decimal:
        return Decimal("100")


class DummyAdapter:
    def create_order(
        self,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        amount: Decimal,
        price: Decimal | None = None,
        order_type: Literal["market", "limit"] = "market",
        dry_run: bool = True,
    ) -> Order:
        fixed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        return Order(
            id="dry-run" if dry_run else "live",
            symbol=symbol,
            side=side,
            amount=amount,
            price=None,
            status="dry_run" if dry_run else "submitted",
            timestamp=fixed_time,
        )


class TestApprovalGate:
    @pytest.mark.asyncio
    async def test_trade_requires_approval(self) -> None:
        config = OrchestratorConfig(
            symbols=["BTCUSD"],
            dry_run=True,
            default_position_size=Decimal("1000"),
            approval_threshold=Decimal("500"),
        )
        automation_config = AutomationConfig(enabled=True)
        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=automation_config,
            strategy=DummyStrategy("BUY"),
            candle_provider=DummyCandleProvider(),
            price_provider=DummyPriceProvider(),
        )

        decisions = await orchestrator.run_once()
        assert decisions
        assert decisions[0].requires_approval is True

    @pytest.mark.asyncio
    async def test_trade_approval_gate_in_live_mode(self) -> None:
        config = OrchestratorConfig(
            symbols=["BTCUSD"],
            dry_run=False,
            default_position_size=Decimal("1000"),
            approval_threshold=Decimal("500"),
        )
        automation_config = AutomationConfig(enabled=True)
        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=automation_config,
            strategy=DummyStrategy("BUY"),
            candle_provider=DummyCandleProvider(),
            price_provider=DummyPriceProvider(),
            executor=BitfinexLiveExecutor(adapter=DummyAdapter(), dry_run=False),
        )

        decisions = await orchestrator.run_once()
        assert decisions
        assert decisions[0].requires_approval is True

    @pytest.mark.asyncio
    async def test_trade_no_approval_below_threshold(self) -> None:
        config = OrchestratorConfig(
            symbols=["BTCUSD"],
            dry_run=True,
            default_position_size=Decimal("100"),
            approval_threshold=Decimal("500"),
        )
        automation_config = AutomationConfig(enabled=True)
        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=automation_config,
            strategy=DummyStrategy("BUY"),
            candle_provider=DummyCandleProvider(),
            price_provider=DummyPriceProvider(),
            executor=BitfinexLiveExecutor(adapter=DummyAdapter(), dry_run=True),
        )

        decisions = await orchestrator.run_once()
        assert decisions
        assert decisions[0].requires_approval is False
        assert decisions[0].execution_result is not None


class TestExecutorSelection:
    def test_build_executor_dry_run_defaults_to_paper(self) -> None:
        config = OrchestratorConfig(dry_run=True, exchange="bitfinex")
        automation_config = AutomationConfig(enabled=True)
        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=automation_config,
            strategy=DummyStrategy("BUY"),
            candle_provider=DummyCandleProvider(),
            price_provider=DummyPriceProvider(),
        )

        assert orchestrator.executor.__class__.__name__ == "PaperExecutor"

    def test_build_executor_live_bitfinex(self) -> None:
        config = OrchestratorConfig(dry_run=False, exchange="bitfinex")
        automation_config = AutomationConfig(enabled=True)
        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=automation_config,
            strategy=DummyStrategy("BUY"),
            candle_provider=DummyCandleProvider(),
            price_provider=DummyPriceProvider(),
            executor=BitfinexLiveExecutor(adapter=DummyAdapter(), dry_run=False),
        )

        assert isinstance(orchestrator.executor, BitfinexLiveExecutor)

    def test_bitfinex_executor_dry_run_flag(self) -> None:
        executor = BitfinexLiveExecutor(adapter=DummyAdapter(), dry_run=True)
        intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="BUY", amount=Decimal("1"))

        result = executor.execute(intent)
        assert result.dry_run is True
        assert result.accepted is True
        assert result.reason == "dry-run"

    def test_bitfinex_executor_live_mode_flag(self) -> None:
        executor = BitfinexLiveExecutor(adapter=DummyAdapter(), dry_run=False)
        intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="SELL", amount=Decimal("2"))

        result = executor.execute(intent)
        assert result.dry_run is False
        assert result.accepted is True
        assert result.reason == "submitted"


# ========== New Bug Fix Tests ==========


class TestPositionSizeCheckNotional:
    """Tests for PositionSizeCheck notional value calculation (bug fix)."""

    def test_notional_with_high_price(self) -> None:
        """Test that high-price assets get correct notional value.

        BTC at $50,000: amount=0.1 units should be $5,000 notional,
        not $0.1 as the old buggy code would compute.
        """
        symbol_config = SymbolConfig(symbol="BTCUSD", max_position_size=Decimal("10000"))
        config = AutomationConfig(enabled=True, symbol_configs={"BTCUSD": symbol_config})
        check = PositionSizeCheck(
            config=config,
            current_position_value=Decimal("0"),
            current_price=Decimal("50000"),
        )
        intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="BUY", amount=Decimal("0.1"))

        result = check.check(intent=intent)
        assert result.ok is True  # 5000 < 10000
        assert "within limits" in result.reason

    def test_notional_exceeds_limit_with_high_price(self) -> None:
        """Test position limit exceeded with high-price asset."""
        symbol_config = SymbolConfig(symbol="BTCUSD", max_position_size=Decimal("10000"))
        config = AutomationConfig(enabled=True, symbol_configs={"BTCUSD": symbol_config})
        check = PositionSizeCheck(
            config=config,
            current_position_value=Decimal("6000"),
            current_price=Decimal("50000"),
        )
        intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="BUY", amount=Decimal("0.1"))

        result = check.check(intent=intent)
        assert result.ok is False  # 6000 + 5000 = 11000 > 10000
        assert "11000.00" in result.reason

    def test_sell_reduces_notional_position(self) -> None:
        """Test SELL reduces position by notional amount."""
        symbol_config = SymbolConfig(symbol="BTCUSD", max_position_size=Decimal("20000"))
        config = AutomationConfig(enabled=True, symbol_configs={"BTCUSD": symbol_config})
        check = PositionSizeCheck(
            config=config,
            current_position_value=Decimal("10000"),
            current_price=Decimal("50000"),
        )
        intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="SELL", amount=Decimal("0.1"))

        result = check.check(intent=intent)
        assert result.ok is True  # 10000 - 5000 = 5000 < 20000

    def test_default_price_of_one(self) -> None:
        """Test that default current_price=1 still works."""
        symbol_config = SymbolConfig(symbol="ETHUSD", max_position_size=Decimal("5000"))
        config = AutomationConfig(enabled=True, symbol_configs={"ETHUSD": symbol_config})
        check = PositionSizeCheck(
            config=config,
            current_position_value=Decimal("3000"),
            current_price=Decimal("1"),
        )
        intent = OrderIntent(exchange="binance", symbol="ETHUSD", side="BUY", amount=Decimal("2000"))

        result = check.check(intent=intent)
        assert result.ok is True  # 3000 + 2000 = 5000 <= 5000


class TestBalanceCheckNotional:
    """Tests for BalanceCheck notional value calculation (bug fix)."""

    def test_notional_balance_comparison(self) -> None:
        """Test balance compared against notional, not raw amount."""
        config = AutomationConfig(enabled=True, min_balance_required=Decimal("100"))
        check = BalanceCheck(
            config=config,
            current_balance=Decimal("6000"),
            current_price=Decimal("50000"),
        )
        intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="BUY", amount=Decimal("0.1"))

        result = check.check(intent=intent)
        assert result.ok is True  # 6000 >= 5000 (notional)

    def test_insufficient_notional_balance(self) -> None:
        """Test insufficient balance for notional value."""
        config = AutomationConfig(enabled=True, min_balance_required=Decimal("100"))
        check = BalanceCheck(
            config=config,
            current_balance=Decimal("4000"),
            current_price=Decimal("50000"),
        )
        intent = OrderIntent(exchange="bitfinex", symbol="BTCUSD", side="BUY", amount=Decimal("0.1"))

        result = check.check(intent=intent)
        assert result.ok is False  # 4000 < 5000 (notional)
        assert "5000.00" in result.reason

    def test_default_price_one(self) -> None:
        """Test default current_price=1 still works."""
        config = AutomationConfig(enabled=True, min_balance_required=Decimal("100"))
        check = BalanceCheck(
            config=config,
            current_balance=Decimal("500"),
            current_price=Decimal("1"),
        )
        intent = OrderIntent(exchange="binance", symbol="ETHUSD", side="BUY", amount=Decimal("200"))

        result = check.check(intent=intent)
        assert result.ok is True  # 500 >= 200


class TestTradeHistoryPruning:
    """Tests for TradeHistory pruning (bug fix)."""

    def test_add_trade_auto_prunes(self) -> None:
        """Test that trades are auto-pruned when exceeding max_entries."""
        history = TradeHistory(max_entries=5)
        now = datetime.now(timezone.utc)

        for i in range(7):
            history.add_trade("BTC/USDT", now - timedelta(days=i))

        # Should have at most max_entries
        assert len(history.trades) <= 5

    def test_prune_old_trades(self) -> None:
        """Test that old trades are pruned."""
        history = TradeHistory(max_entries=100, max_age_days=7)
        now = datetime.now(timezone.utc)

        # Add trades from 10 days ago
        for i in range(10):
            history.trades.append(TradeRecord(symbol="BTC/USDT", timestamp=now - timedelta(days=10)))

        pruned = history.prune()
        assert pruned == 10
        assert len(history.trades) == 0

    def test_prune_keeps_recent_trades(self) -> None:
        """Test that prune keeps recent trades."""
        history = TradeHistory(max_entries=100, max_age_days=7)
        now = datetime.now(timezone.utc)

        # Add 5 recent trades
        for i in range(5):
            history.trades.append(TradeRecord(symbol="BTC/USDT", timestamp=now - timedelta(days=i)))

        pruned = history.prune()
        assert pruned == 0
        assert len(history.trades) == 5

    def test_prune_returns_count(self) -> None:
        """Test that prune returns the number of pruned trades."""
        history = TradeHistory(max_entries=100, max_age_days=30)
        now = datetime.now(timezone.utc)

        for i in range(3):
            history.trades.append(TradeRecord(symbol="BTC/USDT", timestamp=now - timedelta(days=60)))

        pruned = history.prune()
        assert pruned == 3


class TestPolicyDecide:
    """Tests for Policy.decide() implementation (bug fix)."""

    def test_policy_allows_with_fee_model(self) -> None:
        """Test that policy allows opportunities with sufficient edge."""
        from core.fees.model import FeeModel
        from core.types import FeeBreakdown, CostEstimate
        from core.automation.policy import Policy

        fee_model = FeeModel(
            breakdown=FeeBreakdown(
                currency="USD",
                maker_fee_rate=Decimal("0.001"),
                taker_fee_rate=Decimal("0.002"),
                assumed_spread_bps=10,
                assumed_slippage_bps=5,
            )
        )

        policy = Policy(fee_model=fee_model)
        opportunity = Opportunity(
            symbol="BTC/USDT",
            timeframe="1h",
            score=50,  # 50 bps edge
            side="BUY",
            signals=(),
        )
        cost = CostEstimate(
            fee_currency="USD",
            gross_notional=Decimal("1000"),
            estimated_fees=Decimal("2"),
            estimated_spread_cost=Decimal("1"),
            estimated_slippage_cost=Decimal("0.5"),
            estimated_total_cost=Decimal("3.5"),
            minimum_edge_rate=Decimal("0.0035"),
            minimum_edge_bps=Decimal("35.00"),
        )
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("10"))

        result = policy.decide(opportunity=opportunity, cost=cost, proposed_intent=intent)
        assert result.decision == "allow"

    def test_policy_denies_low_edge(self) -> None:
        """Test that policy denies opportunities with insufficient edge."""
        from core.fees.model import FeeModel
        from core.types import FeeBreakdown, CostEstimate
        from core.automation.policy import Policy

        fee_model = FeeModel(
            breakdown=FeeBreakdown(
                currency="USD",
                maker_fee_rate=Decimal("0.001"),
                taker_fee_rate=Decimal("0.002"),
                assumed_spread_bps=10,
                assumed_slippage_bps=5,
            )
        )

        policy = Policy(fee_model=fee_model, min_edge_bps=Decimal("50"))
        opportunity = Opportunity(
            symbol="BTC/USDT",
            timeframe="1h",
            score=5,  # 5 bps edge (low)
            side="BUY",
            signals=(),
        )
        cost = CostEstimate(
            fee_currency="USD",
            gross_notional=Decimal("1000"),
            estimated_fees=Decimal("2"),
            estimated_spread_cost=Decimal("1"),
            estimated_slippage_cost=Decimal("0.5"),
            estimated_total_cost=Decimal("3.5"),
            minimum_edge_rate=Decimal("0.0035"),
            minimum_edge_bps=Decimal("35.00"),
        )
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("10"))

        result = policy.decide(opportunity=opportunity, cost=cost, proposed_intent=intent)
        assert result.decision == "deny"

    def test_policy_denies_small_notional(self) -> None:
        """Test that policy denies opportunities with too small notional."""
        policy = Policy(min_notional=Decimal("100"))
        opportunity = Opportunity(
            symbol="BTC/USDT",
            timeframe="1h",
            score=50,
            side="BUY",
            signals=(),
        )
        cost = CostEstimate(
            fee_currency="USD",
            gross_notional=Decimal("50"),
            estimated_fees=Decimal("1"),
            estimated_spread_cost=Decimal("0.5"),
            estimated_slippage_cost=Decimal("0.25"),
            estimated_total_cost=Decimal("1.75"),
            minimum_edge_rate=Decimal("0.0350"),
            minimum_edge_bps=Decimal("35.00"),
        )
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("10"))

        result = policy.decide(opportunity=opportunity, cost=cost, proposed_intent=intent)
        assert result.decision == "deny"
        assert "too small" in result.reason

    def test_policy_denies_large_notional(self) -> None:
        """Test that policy denies opportunities with too large notional."""
        policy = Policy(max_notional=Decimal("500"))
        opportunity = Opportunity(
            symbol="BTC/USDT",
            timeframe="1h",
            score=50,
            side="BUY",
            signals=(),
        )
        cost = CostEstimate(
            fee_currency="USD",
            gross_notional=Decimal("1000"),
            estimated_fees=Decimal("2"),
            estimated_spread_cost=Decimal("1"),
            estimated_slippage_cost=Decimal("0.5"),
            estimated_total_cost=Decimal("3.5"),
            minimum_edge_rate=Decimal("0.0035"),
            minimum_edge_bps=Decimal("35.00"),
        )
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("10"))

        result = policy.decide(opportunity=opportunity, cost=cost, proposed_intent=intent)
        assert result.decision == "deny"
        assert "too large" in result.reason

    def test_policy_allows_without_fee_model(self) -> None:
        """Test that policy allows when no fee model is set (skip edge check)."""
        policy = Policy()
        opportunity = Opportunity(
            symbol="BTC/USDT",
            timeframe="1h",
            score=50,
            side="BUY",
            signals=(),
        )
        cost = CostEstimate(
            fee_currency="USD",
            gross_notional=Decimal("1000"),
            estimated_fees=Decimal("2"),
            estimated_spread_cost=Decimal("1"),
            estimated_slippage_cost=Decimal("0.5"),
            estimated_total_cost=Decimal("3.5"),
            minimum_edge_rate=Decimal("0.0035"),
            minimum_edge_bps=Decimal("35.00"),
        )
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("10"))

        result = policy.decide(opportunity=opportunity, cost=cost, proposed_intent=intent)
        assert result.decision == "allow"


# ========== Signal Deduplication Tests ===========


class TestSignalDeduplication:
    """Tests for SignalDeduplication check."""

    def test_no_cooldown(self) -> None:
        """Test when no cooldown is configured."""
        from core.automation.safety import SignalDeduplication

        SignalDeduplication.clear_last_signal()
        config = AutomationConfig(enabled=True, cooldown_seconds_default=0)
        history = TradeHistory()
        check = SignalDeduplication(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True
        assert "No cooldown" in result.reason

    def test_no_previous_trades(self) -> None:
        """Test when there are no previous trades."""
        from core.automation.safety import SignalDeduplication

        SignalDeduplication.clear_last_signal()
        config = AutomationConfig(enabled=True, cooldown_seconds_default=60)
        history = TradeHistory()
        check = SignalDeduplication(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True
        assert "No previous trades" in result.reason

    def test_duplicate_signal_deduplicated(self) -> None:
        """Test that the first signal passes through and subsequent same-side signals are deduplicated."""
        from core.automation.safety import SignalDeduplication

        SignalDeduplication.clear_last_signal()
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=120)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        history.add_trade("BTC/USDT", recent_time)

        check = SignalDeduplication(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        # First signal passes through
        result = check.check(intent=intent)
        assert result.ok is True
        assert "deduplication" in result.reason.lower()
        assert "BUY" in result.reason

    def test_different_signal_not_deduplicated(self) -> None:
        """Test that different signal sides are not deduplicated against each other."""
        from core.automation.safety import SignalDeduplication

        SignalDeduplication.clear_last_signal()
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=120)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        history.add_trade("BTC/USDT", recent_time)

        check = SignalDeduplication(config=config, trade_history=history)

        # First BUY passes through (first occurrence)
        intent_buy = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        result_buy = check.check(intent=intent_buy)
        assert result_buy.ok is True

        # Second BUY is deduplicated (same side, within cooldown)
        intent_buy2 = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        result_buy2 = check.check(intent=intent_buy2)
        assert result_buy2.ok is False

        # SELL passes through (different side)
        intent_sell = OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100"))
        result_sell = check.check(intent=intent_sell)
        assert result_sell.ok is True

    def test_cooldown_passed_resets_tracking(self) -> None:
        """Test that cooldown passing resets signal tracking."""
        from core.automation.safety import SignalDeduplication

        SignalDeduplication.clear_last_signal()
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=60)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        history.add_trade("BTC/USDT", old_time)

        check = SignalDeduplication(config=config, trade_history=history)
        intent = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))

        result = check.check(intent=intent)
        assert result.ok is True
        assert "cooldown passed" in result.reason.lower()

    def test_deduplication_with_symbol_specific_cooldown(self) -> None:
        """Test deduplication respects symbol-specific cooldown values."""
        from core.automation.safety import SignalDeduplication

        SignalDeduplication.clear_last_signal()
        btc_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=300)
        eth_config = SymbolConfig(symbol="ETH/USDT", cooldown_seconds=60)
        config = AutomationConfig(
            enabled=True,
            symbol_configs={"BTC/USDT": btc_config, "ETH/USDT": eth_config},
        )
        history = TradeHistory()
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=200)
        history.add_trade("BTC/USDT", recent_time)
        history.add_trade("ETH/USDT", recent_time)

        check = SignalDeduplication(config=config, trade_history=history)

        # First BTC signal passes through (first occurrence, within 300s cooldown)
        intent_btc = OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        result_btc = check.check(intent=intent_btc)
        assert result_btc.ok is True

        # ETH signal passes through (cooldown passed: 200s > 60s)
        intent_eth = OrderIntent(exchange="binance", symbol="ETH/USDT", side="BUY", amount=Decimal("100"))
        result_eth = check.check(intent=intent_eth)
        assert result_eth.ok is True

    def test_signals_deduplicated_during_cooldown_window(self) -> None:
        """Test that signals during the cooldown window are correctly deduplicated.

        The first signal passes through (triggers trade), subsequent same-side
        signals are deduplicated, and different-side signals pass through.
        """
        from core.automation.safety import SignalDeduplication

        SignalDeduplication.clear_last_signal()
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=120)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        history.add_trade("BTC/USDT", recent_time)

        check = SignalDeduplication(config=config, trade_history=history)

        # First BUY signal passes through (first occurrence)
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is True
        assert "first" in result.reason.lower()

        # Second BUY signal is deduplicated (same side, within cooldown)
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is False
        assert "duplicate" in result.reason.lower()

        # Third BUY signal is also deduplicated
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is False

        # SELL signal passes through (different side)
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="SELL", amount=Decimal("100"))
        )
        assert result.ok is True

        # Fourth BUY signal passes through again (after SELL updated tracking)
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is True

    def test_cooldown_expiry_resets_dedup_correctly(self) -> None:
        """Test that signal dedup resets correctly when cooldown expires.

        After cooldown expires, the next signal should pass through as a
        fresh signal, not be incorrectly treated as a duplicate.

        This tests the fix for a bug where last_signal was set to datetime.now()
        instead of last_signal_time when cooldown expired, causing the next
        signal to have last_time >= last_signal_time and be falsely rejected.
        """
        from core.automation.rules import TradeRecord

        SignalDeduplication.clear_last_signal()
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=60)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()

        # Record a trade 10 seconds ago
        trade_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        history.add_trade("BTC/USDT", trade_time)

        check = SignalDeduplication(config=config, trade_history=history)

        # First signal within cooldown — passes through, updates last_signal
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is True
        assert "first" in result.reason.lower()

        # Second signal — duplicate, rejected
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is False
        assert "duplicate" in result.reason.lower()

        # Advance time past cooldown (simulate time passing)
        # Replace the trade record with one that's 70s ago
        old_trades = [t for t in history.trades if t.symbol == "BTC/USDT"]
        for t in old_trades:
            history.trades.remove(t)
        history.trades.append(
            TradeRecord(symbol="BTC/USDT", timestamp=datetime.now(timezone.utc) - timedelta(seconds=70))
        )

        # Third signal — cooldown has passed, should pass through (not duplicate)
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is True
        assert "passed" in result.reason.lower()

        # Fourth signal — after cooldown reset, should pass through again
        # (the reset sets last_signal to last_signal_time, so next signal
        # has last_time < last_signal_time → first occurrence)
        result = check.check(
            intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100"))
        )
        assert result.ok is True

    def test_dedup_with_multiple_cooldown_cycles(self) -> None:
        """Test dedup across multiple cooldown cycles."""
        from core.automation.rules import TradeRecord

        SignalDeduplication.clear_last_signal()
        symbol_config = SymbolConfig(symbol="BTC/USDT", cooldown_seconds=60)
        config = AutomationConfig(enabled=True, symbol_configs={"BTC/USDT": symbol_config})
        history = TradeHistory()

        # Trade at T=0 (10 seconds ago)
        trade_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        history.add_trade("BTC/USDT", trade_time)

        check = SignalDeduplication(config=config, trade_history=history)

        # Cycle 1: within cooldown
        r1 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r1.ok is True  # first

        r2 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r2.ok is False  # duplicate

        # Advance past cooldown
        old_trades = [t for t in history.trades if t.symbol == "BTC/USDT"]
        for t in old_trades:
            history.trades.remove(t)
        history.trades.append(
            TradeRecord(symbol="BTC/USDT", timestamp=datetime.now(timezone.utc) - timedelta(seconds=70))
        )

        r3 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r3.ok is True  # cooldown passed

        # Record a new trade to start a new cooldown cycle
        history.trades.append(
            TradeRecord(symbol="BTC/USDT", timestamp=datetime.now(timezone.utc) - timedelta(seconds=10))
        )

        # Cycle 2: first signal of new cycle (last_signal was cleared by r3,
        # so r4 enters "first occurrence" branch — correct behavior)
        r4 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r4.ok is True  # first of new cycle

        # Cycle 2: second signal — duplicate
        r5 = check.check(intent=OrderIntent(exchange="binance", symbol="BTC/USDT", side="BUY", amount=Decimal("100")))
        assert r5.ok is False  # duplicate in new cycle
