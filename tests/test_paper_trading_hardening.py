"""Tests for paper trading hardening.

Covers:
- FeeModel with realistic defaults
- PaperExecutor fee application, slippage, partial/missed fills
- Position sizing (half-Kelly default)
- DrawdownCheck and DrawdownMonitor integration
- ExposureChecker integration
- Audit logging enrichment
- PortfolioManager summary with drawdown and exposure
"""

from __future__ import annotations

from decimal import Decimal


from core.automation.audit import AuditLogger
from core.automation.rules import AutomationConfig
from core.automation.safety import (
    DrawdownCheck,
)
from core.automation.orchestrator import (
    OrchestratorConfig,
    StrategyOrchestrator,
)
from core.execution.paper import (
    FeeModel,
    PaperExecutor,
)
from core.fees.model import DEFAULT_FEE_BREAKDOWN
from core.risk.drawdown import DrawdownConfig, DrawdownMonitor
from core.risk.limits import ExposureChecker, ExposureLimits
from core.risk.sizing import PositionSize, calculate_position_size
from core.types import OrderIntent


# ========== FeeModel Tests ==========


class TestFeeModelDefaults:
    def test_default_breakdown_values(self):
        """FeeModel should have Bitfinex-like defaults."""
        model = FeeModel()
        assert model.breakdown.taker_fee_rate == Decimal("0.002")
        assert model.breakdown.maker_fee_rate == Decimal("0.001")
        assert model.breakdown.assumed_spread_bps == 10
        assert model.breakdown.assumed_slippage_bps == 5

    def test_estimate_cost_taker(self):
        """Taker (market) orders should use taker fee rate."""
        model = FeeModel()
        cost = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)
        # fee = 1000 * 0.002 = 2.0
        # spread = 1000 * 10 / 10000 = 1.0
        # slippage = 1000 * 5 / 10000 = 0.5
        # total = 3.5
        assert cost.estimated_fees == Decimal("2.000000")
        assert cost.estimated_spread_cost == Decimal("1.000000")
        assert cost.estimated_slippage_cost == Decimal("0.500000")
        assert cost.estimated_total_cost == Decimal("3.500000")

    def test_estimate_cost_maker(self):
        """Maker (limit) orders should use maker fee rate."""
        model = FeeModel()
        cost = model.estimate_cost(gross_notional=Decimal("1000"), taker=False)
        # fee = 1000 * 0.001 = 1.0
        assert cost.estimated_fees == Decimal("1.000000")
        assert cost.estimated_total_cost == Decimal("2.500000")

    def test_minimum_edge_bps(self):
        """Minimum edge should be total cost / notional in bps."""
        model = FeeModel()
        cost = model.estimate_cost(gross_notional=Decimal("1000"), taker=True)
        # 3.5 / 1000 = 0.0035 = 35 bps
        assert cost.minimum_edge_bps == Decimal("35.00")


# ========== PaperExecutor Tests ==========


class TestPaperExecutorFees:
    def test_fees_applied_to_market_orders(self):
        """Market orders should deduct fees from P&L."""
        executor = PaperExecutor()
        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="market",
            market_price=Decimal("50000"),
        )

        assert order.status in ("FILLED", "PARTIAL")
        assert order.fees > 0

    def test_fees_by_symbol(self):
        """Fees should be tracked per symbol."""
        executor = PaperExecutor()
        executor.execute_paper_order("BTCUSD", "BUY", Decimal("1"), "market", market_price=Decimal("50000"))
        executor.execute_paper_order("ETHUSD", "BUY", Decimal("10"), "market", market_price=Decimal("3000"))

        btc_fees = executor.get_fees_by_symbol("BTCUSD")
        eth_fees = executor.get_fees_by_symbol("ETHUSD")

        assert btc_fees > 0
        assert eth_fees > 0
        assert executor.get_total_fees() == btc_fees + eth_fees

    def test_unrealized_pnl_includes_fees(self):
        """Unrealized P&L should account for fees paid."""
        executor = PaperExecutor()
        executor.execute_paper_order("BTCUSD", "BUY", Decimal("1"), "market", market_price=Decimal("50000"))

        # Price goes up to 51000
        unrealized = executor.get_unrealized_pnl("BTCUSD", Decimal("51000"))
        # Should be positive (price went up) minus fees
        assert unrealized < (Decimal("51000") - Decimal("50000"))

    def test_fee_model_wired(self):
        """PaperExecutor should use FeeModel."""
        model = FeeModel()
        executor = PaperExecutor(fee_model=model)
        assert executor.get_fee_model() is model

    def test_custom_fee_model(self):
        """Custom fee model should be used."""
        custom_breakdown = DEFAULT_FEE_BREAKDOWN.__class__(
            currency="USD",
            maker_fee_rate=Decimal("0.0005"),
            taker_fee_rate=Decimal("0.0015"),
            assumed_spread_bps=5,
            assumed_slippage_bps=3,
        )
        model = FeeModel(breakdown=custom_breakdown)
        executor = PaperExecutor(fee_model=model)

        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="market",
            market_price=Decimal("50000"),
        )
        assert order.fees > 0


class TestPaperExecutorPartialMissedFills:
    def test_partial_fill(self):
        """Some market orders should partially fill."""
        # Use a fee model that gives deterministic partial fills
        executor = PaperExecutor(
            partial_fill_prob=Decimal("0.9"),
            missed_fill_prob=Decimal("0.01"),
        )

        # Execute many orders to get partial fills
        partial_count = 0
        for _ in range(20):
            order = executor.execute_paper_order(
                symbol="BTCUSD",
                side="BUY",
                qty=Decimal("1"),
                order_type="market",
                market_price=Decimal("50000"),
            )
            if order.status == "PARTIAL":
                partial_count += 1
                assert order.fill_qty is not None
                assert order.fill_qty < order.qty
                assert order.fill_ratio is not None
                assert order.fill_ratio < Decimal("1")

        # Should have some partial fills
        assert partial_count > 0, "Expected at least one partial fill"

    def test_mixed_fill_statuses(self):
        """Orders should have FILLED, PARTIAL, MISSED, PENDING statuses."""
        executor = PaperExecutor(
            partial_fill_prob=Decimal("0.5"),
            missed_fill_prob=Decimal("0.1"),
        )

        # Execute a mix of market and limit orders
        market_order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="market",
            market_price=Decimal("50000"),
        )
        limit_order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("49500"),
        )

        assert market_order.status in ("FILLED", "PARTIAL", "MISSED")
        assert limit_order.status == "PENDING"
        assert market_order.fill_price is not None
        # Limit orders have fill_price set to limit_price in the constructor
        assert limit_order.fill_price is not None

    def test_fill_ratio_for_partial(self):
        """Partial fills should have fill_ratio between min_fill_ratio and 1.0."""
        executor = PaperExecutor(
            min_fill_ratio=Decimal("0.5"),
            partial_fill_prob=Decimal("0.9"),
            missed_fill_prob=Decimal("0.01"),
        )

        for _ in range(30):
            order = executor.execute_paper_order(
                symbol="BTCUSD",
                side="BUY",
                qty=Decimal("1"),
                order_type="market",
                market_price=Decimal("50000"),
            )
            if order.status == "PARTIAL":
                assert order.fill_ratio is not None
                assert order.fill_ratio >= executor._min_fill_ratio
                assert order.fill_ratio <= Decimal("1")


class TestPaperExecutorSummary:
    def test_paper_summary(self):
        """get_paper_summary should return comprehensive state."""
        executor = PaperExecutor()
        executor.execute_paper_order("BTCUSD", "BUY", Decimal("1"), "market", market_price=Decimal("50000"))
        executor.execute_paper_order("ETHUSD", "BUY", Decimal("10"), "market", market_price=Decimal("3000"))

        summary = executor.get_paper_summary()

        assert "total_fees" in summary
        assert "total_unrealized_pnl" in summary
        assert "positions" in summary
        assert "orders" in summary
        assert "fee_model" in summary
        assert summary["orders"]["total"] == 2
        assert "maker_fee" in summary["fee_model"]
        assert "taker_fee" in summary["fee_model"]


# ========== Position Sizing Tests ==========


class TestPositionSizing:
    def test_half_kelly_default(self):
        """Position sizing should use half-Kelly (0.5) by default."""
        config = PositionSize(
            method="kelly",
            win_rate=Decimal("0.6"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            # kelly_fraction not set -> should default to 0.5
        )
        size = calculate_position_size(
            config=config,
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("49000"),
        )
        assert size > 0

    def test_half_kelly_vs_full_kelly(self):
        """Half-Kelly should produce half the size of full Kelly."""
        half_config = PositionSize(
            method="kelly",
            win_rate=Decimal("0.6"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            kelly_fraction=Decimal("0.5"),
        )
        full_config = PositionSize(
            method="kelly",
            win_rate=Decimal("0.6"),
            avg_win=Decimal("100"),
            avg_loss=Decimal("50"),
            kelly_fraction=Decimal("1.0"),
        )

        half_size = calculate_position_size(
            config=half_config,
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("49000"),
        )
        full_size = calculate_position_size(
            config=full_config,
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("49000"),
        )

        # Half-Kelly should be roughly half of full Kelly
        assert half_size < full_size

    def test_fixed_fractional(self):
        """Fixed fractional sizing should work."""
        config = PositionSize(
            method="fixed",
            portfolio_percent=Decimal("0.02"),  # 2% of portfolio
        )
        size = calculate_position_size(
            config=config,
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("49000"),
        )
        # risk = 10000 * 0.02 = 200
        # risk_per_unit = 1000
        # size = 200 / 1000 = 0.2
        assert size == Decimal("0.2")


# ========== Drawdown Tests ==========


class TestDrawdownCheck:
    def test_drawdown_check_allows_when_within_limits(self):
        """DrawdownCheck should allow trades when within limits."""
        check = DrawdownCheck(
            trading_paused=False,
            daily_drawdown_pct=Decimal("0.02"),
            total_drawdown_pct=Decimal("0.03"),
            max_daily_drawdown=Decimal("0.05"),
            max_total_drawdown=Decimal("0.10"),
        )
        result = check.check(
            intent=OrderIntent(
                exchange="bitfinex",
                symbol="BTCUSD",
                side="BUY",
                amount=Decimal("1"),
            )
        )
        assert result.ok
        assert "OK" in result.reason

    def test_drawdown_check_blocks_when_daily_exceeded(self):
        """DrawdownCheck should block when daily drawdown exceeded."""
        check = DrawdownCheck(
            trading_paused=False,
            daily_drawdown_pct=Decimal("0.06"),
            total_drawdown_pct=Decimal("0.03"),
            max_daily_drawdown=Decimal("0.05"),
            max_total_drawdown=Decimal("0.10"),
        )
        result = check.check(
            intent=OrderIntent(
                exchange="bitfinex",
                symbol="BTCUSD",
                side="BUY",
                amount=Decimal("1"),
            )
        )
        assert not result.ok
        assert "Daily drawdown" in result.reason

    def test_drawdown_check_blocks_when_total_exceeded(self):
        """DrawdownCheck should block when total drawdown exceeded."""
        check = DrawdownCheck(
            trading_paused=False,
            daily_drawdown_pct=Decimal("0.02"),
            total_drawdown_pct=Decimal("0.12"),
            max_daily_drawdown=Decimal("0.05"),
            max_total_drawdown=Decimal("0.10"),
        )
        result = check.check(
            intent=OrderIntent(
                exchange="bitfinex",
                symbol="BTCUSD",
                side="BUY",
                amount=Decimal("1"),
            )
        )
        assert not result.ok
        assert "Total drawdown" in result.reason

    def test_drawdown_check_blocks_when_trading_paused(self):
        """DrawdownCheck should block when trading is paused."""
        check = DrawdownCheck(
            trading_paused=True,
            daily_drawdown_pct=Decimal("0.02"),
            total_drawdown_pct=Decimal("0.03"),
        )
        result = check.check(
            intent=OrderIntent(
                exchange="bitfinex",
                symbol="BTCUSD",
                side="BUY",
                amount=Decimal("1"),
            )
        )
        assert not result.ok
        assert "Trading paused" in result.reason


class TestDrawdownMonitor:
    def test_daily_drawdown_tracking(self):
        """DrawdownMonitor should track daily drawdown."""
        monitor = DrawdownMonitor(
            config=DrawdownConfig(
                max_daily_drawdown=Decimal("0.05"),
            ),
        )
        monitor.update_balance(Decimal("10000"))
        monitor.update_balance(Decimal("9500"))  # 5% drawdown

        dd = monitor.get_daily_drawdown()
        assert dd == Decimal("0.05")
        # 5% drawdown with 5% limit: check uses >, so 5.0% is not exceeded
        # but the test is about tracking, not exact boundary
        assert dd >= Decimal("0.05")

    def test_total_drawdown_tracking(self):
        """DrawdownMonitor should track total drawdown."""
        monitor = DrawdownMonitor(
            config=DrawdownConfig(
                max_total_drawdown=Decimal("0.10"),
            ),
        )
        monitor.update_balance(Decimal("10000"))
        monitor.update_balance(Decimal("9000"))  # 10% drawdown

        td = monitor.get_total_drawdown()
        assert td == Decimal("0.10")
        assert td >= Decimal("0.10")

    def test_trading_paused_on_exceeded(self):
        """Trading should pause when drawdown limits exceeded."""
        monitor = DrawdownMonitor(
            config=DrawdownConfig(
                max_daily_drawdown=Decimal("0.03"),
            ),
        )
        monitor.update_balance(Decimal("10000"))
        monitor.update_balance(Decimal("9600"))  # 4% > 3%

        assert monitor.state.trading_paused
        assert monitor.is_trading_allowed() is False


# ========== Exposure Tests ==========


class TestExposureChecker:
    def test_position_size_check(self):
        """ExposureChecker should check position size limits."""
        checker = ExposureChecker(
            limits=ExposureLimits(
                max_position_size_per_symbol=Decimal("5000"),
            ),
        )
        allowed, reason = checker.check_position_size("BTCUSD", Decimal("4000"))
        assert allowed
        assert reason is None

        allowed, reason = checker.check_position_size("BTCUSD", Decimal("6000"))
        assert not allowed
        assert reason is not None and "exceeds max" in reason

    def test_total_exposure_check(self):
        """ExposureChecker should check total exposure limits."""
        checker = ExposureChecker(
            limits=ExposureLimits(
                max_total_exposure=Decimal("0.9"),
            ),
        )
        allowed, reason = checker.check_total_exposure(
            current_exposure=Decimal("7000"),
            portfolio_value=Decimal("10000"),
            new_position_value=Decimal("1500"),
        )
        assert allowed  # 8500/10000 = 85% < 90%

        allowed, reason = checker.check_total_exposure(
            current_exposure=Decimal("7000"),
            portfolio_value=Decimal("10000"),
            new_position_value=Decimal("3000"),
        )
        assert not allowed  # 10000/10000 = 100% > 90%

    def test_position_count_check(self):
        """ExposureChecker should check position count limits."""
        checker = ExposureChecker(
            limits=ExposureLimits(
                max_positions=5,
            ),
        )
        allowed, _ = checker.check_position_count(4)
        assert allowed

        allowed, _ = checker.check_position_count(5)
        assert not allowed

    def test_check_all(self):
        """ExposureChecker should check all limits at once."""
        checker = ExposureChecker(
            limits=ExposureLimits(
                max_position_size_per_symbol=Decimal("5000"),
                max_total_exposure=Decimal("0.9"),
                max_positions=5,
            ),
        )
        allowed, reasons = checker.check_all(
            symbol="BTCUSD",
            position_value=Decimal("2000"),
            current_exposure=Decimal("7000"),
            portfolio_value=Decimal("10000"),
            current_positions=3,
        )
        assert allowed
        assert len(reasons) == 0

        allowed, reasons = checker.check_all(
            symbol="BTCUSD",
            position_value=Decimal("6000"),  # exceeds max_position_size
            current_exposure=Decimal("7000"),
            portfolio_value=Decimal("10000"),
            current_positions=3,
        )
        assert not allowed
        assert len(reasons) > 0


# ========== Audit Logging Tests ==========


class TestAuditLogging:
    def test_log_trade_executed_with_fees(self):
        """AuditLogger should include fee details in trade events."""
        logger = AuditLogger()
        logger.log_trade_executed(
            symbol="BTCUSD",
            side="BUY",
            amount="1.0",
            fill_price=Decimal("50000"),
            fees=Decimal("175"),
            slippage_bps=5,
            fill_status="FILLED",
        )

        events = logger.get_events(event_type="trade_executed")
        assert len(events) == 1
        ctx = events[0].context
        assert ctx["fill_price"] == "50000"
        assert ctx["fees"] == "175"
        assert ctx["slippage_bps"] == "5"
        assert ctx["fill_status"] == "FILLED"

    def test_log_trade_executed_without_fees(self):
        """AuditLogger should work without fee details."""
        logger = AuditLogger()
        logger.log_trade_executed(
            symbol="ETHUSD",
            side="SELL",
            amount="10.0",
        )

        events = logger.get_events(event_type="trade_executed")
        assert len(events) == 1
        ctx = events[0].context
        assert ctx["symbol"] == "ETHUSD"
        assert ctx["side"] == "SELL"
        assert ctx["amount"] == "10.0"


# ========== Portfolio Manager Tests ==========


class TestPortfolioManagerSummary:
    def test_summary_includes_total_pnl(self):
        """PortfolioManager summary should include total PnL."""
        from core.portfolio.manager import PortfolioManager, PortfolioConfig

        config = PortfolioConfig(
            quote_currency="USD",
            initial_balance=Decimal("10000"),
        )

        def price_provider(symbol: str) -> Decimal:
            if symbol == "BTCUSD":
                return Decimal("51000")
            return Decimal("3000")

        pm = PortfolioManager(config=config, price_provider=price_provider)
        summary = pm.get_summary()

        assert "total_pnl" in summary
        assert isinstance(summary["total_pnl"], float)
        assert "max_drawdown" in summary
        assert "current_drawdown" in summary


# ========== Orchestrator Integration Tests ==========


class TestOrchestratorIntegration:
    def test_orchestrator_has_drawdown_monitor(self):
        """Orchestrator should have a DrawdownMonitor."""
        config = OrchestratorConfig(
            symbols=["BTCUSD"],
            dry_run=True,
            max_daily_drawdown=Decimal("0.05"),
            max_total_drawdown=Decimal("0.10"),
        )
        auto_config = AutomationConfig(enabled=True)

        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=auto_config,
            strategy=None,  # type: ignore
            candle_provider=None,  # type: ignore
            price_provider=None,  # type: ignore
        )

        assert hasattr(orchestrator, "drawdown_monitor")
        assert orchestrator.drawdown_monitor.config.max_daily_drawdown == Decimal("0.05")
        assert orchestrator.drawdown_monitor.config.max_total_drawdown == Decimal("0.10")

    def test_orchestrator_has_exposure_checker(self):
        """Orchestrator should have an ExposureChecker."""
        config = OrchestratorConfig(
            symbols=["BTCUSD"],
            dry_run=True,
            max_position_size_per_symbol=Decimal("5000"),
            max_total_exposure=Decimal("0.9"),
            max_positions=10,
        )
        auto_config = AutomationConfig(enabled=True)

        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=auto_config,
            strategy=None,  # type: ignore
            candle_provider=None,  # type: ignore
            price_provider=None,  # type: ignore
        )

        assert hasattr(orchestrator, "exposure_checker")
        assert orchestrator.exposure_checker.limits.max_position_size_per_symbol == Decimal("5000")

    def test_safety_checks_include_drawdown(self):
        """_build_safety_checks should include DrawdownCheck."""
        config = OrchestratorConfig(
            symbols=["BTCUSD"],
            dry_run=True,
            max_daily_drawdown=Decimal("0.05"),
            max_total_drawdown=Decimal("0.10"),
        )
        auto_config = AutomationConfig(enabled=True)

        orchestrator = StrategyOrchestrator(
            config=config,
            automation_config=auto_config,
            strategy=None,  # type: ignore
            candle_provider=None,  # type: ignore
            price_provider=None,  # type: ignore
        )

        checks = orchestrator._build_safety_checks("BTCUSD")
        check_names = [type(c).__name__ for c in checks]
        assert "DrawdownCheck" in check_names
        assert "PositionSizeCheck" in check_names
        assert "BalanceCheck" in check_names
        assert "DailyLossCheck" in check_names
        assert "KillSwitchCheck" in check_names
