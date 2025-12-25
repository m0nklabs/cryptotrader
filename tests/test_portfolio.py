"""Tests for portfolio management module."""

from decimal import Decimal

import pytest

from core.portfolio import (
    BalanceManager,
    EquityCurve,
    PortfolioConfig,
    PortfolioManager,
    PortfolioSnapshot,
    PositionManager,
    PositionSide,
)


# ========== BalanceManager Tests ==========


class TestBalanceManager:
    """Tests for BalanceManager."""

    def test_initial_balance(self) -> None:
        """Test initialization with balances."""
        mgr = BalanceManager({"USD": Decimal("10000"), "BTC": Decimal("1")})
        assert mgr.get_available("USD") == Decimal("10000")
        assert mgr.get_available("BTC") == Decimal("1")

    def test_get_balance_creates_zero(self) -> None:
        """Test getting non-existent balance creates zero."""
        mgr = BalanceManager()
        balance = mgr.get_balance("ETH")
        assert balance.available == Decimal("0")
        assert balance.reserved == Decimal("0")

    def test_credit(self) -> None:
        """Test crediting funds."""
        mgr = BalanceManager()
        balance = mgr.credit("USD", Decimal("500"))
        assert balance.available == Decimal("500")

    def test_credit_negative_raises(self) -> None:
        """Test credit with negative amount raises."""
        mgr = BalanceManager()
        with pytest.raises(ValueError, match="positive"):
            mgr.credit("USD", Decimal("-100"))

    def test_debit(self) -> None:
        """Test debiting funds."""
        mgr = BalanceManager({"USD": Decimal("1000")})
        balance = mgr.debit("USD", Decimal("300"))
        assert balance.available == Decimal("700")

    def test_debit_insufficient_raises(self) -> None:
        """Test debit with insufficient balance raises."""
        mgr = BalanceManager({"USD": Decimal("100")})
        with pytest.raises(ValueError, match="Insufficient"):
            mgr.debit("USD", Decimal("500"))

    def test_reserve_and_release(self) -> None:
        """Test reserving and releasing funds."""
        mgr = BalanceManager({"USD": Decimal("1000")})

        # Reserve
        balance = mgr.reserve("USD", Decimal("400"))
        assert balance.available == Decimal("600")
        assert balance.reserved == Decimal("400")
        assert balance.total == Decimal("1000")

        # Release
        balance = mgr.release("USD", Decimal("200"))
        assert balance.available == Decimal("800")
        assert balance.reserved == Decimal("200")

    def test_settle_reserved(self) -> None:
        """Test settling reserved funds."""
        mgr = BalanceManager({"USD": Decimal("1000")})
        mgr.reserve("USD", Decimal("500"))

        balance = mgr.settle_reserved("USD", Decimal("500"))
        assert balance.available == Decimal("500")
        assert balance.reserved == Decimal("0")

    def test_get_all_balances(self) -> None:
        """Test getting all non-zero balances."""
        mgr = BalanceManager({"USD": Decimal("1000"), "BTC": Decimal("0.5")})
        mgr.get_balance("ETH")  # Creates zero balance

        balances = mgr.get_all_balances()
        assert len(balances) == 2
        assets = {b.asset for b in balances}
        assert assets == {"USD", "BTC"}


# ========== PositionManager Tests ==========


class TestPositionManager:
    """Tests for PositionManager."""

    def test_open_long_position(self) -> None:
        """Test opening a long position."""
        mgr = PositionManager()
        position = mgr.open_position(
            symbol="BTC/USD",
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            price=Decimal("50000"),
        )
        assert position.symbol == "BTC/USD"
        assert position.side == PositionSide.LONG
        assert position.quantity == Decimal("1")
        assert position.avg_entry_price == Decimal("50000")

    def test_open_short_position(self) -> None:
        """Test opening a short position."""
        mgr = PositionManager()
        position = mgr.open_position(
            symbol="ETH/USD",
            side=PositionSide.SHORT,
            quantity=Decimal("10"),
            price=Decimal("3000"),
        )
        assert position.side == PositionSide.SHORT
        assert position.quantity == Decimal("10")

    def test_average_in_same_direction(self) -> None:
        """Test averaging into existing position."""
        mgr = PositionManager()
        mgr.open_position("BTC/USD", PositionSide.LONG, Decimal("1"), Decimal("50000"))
        position = mgr.open_position("BTC/USD", PositionSide.LONG, Decimal("1"), Decimal("52000"))

        assert position.quantity == Decimal("2")
        assert position.avg_entry_price == Decimal("51000")  # (50000 + 52000) / 2

    def test_close_position_full(self) -> None:
        """Test fully closing a position."""
        mgr = PositionManager()
        mgr.open_position("BTC/USD", PositionSide.LONG, Decimal("1"), Decimal("50000"))

        closed = mgr.close_position("BTC/USD", Decimal("55000"))
        assert closed.quantity == Decimal("0")
        assert closed.realized_pnl == Decimal("5000")  # 55000 - 50000
        assert mgr.get_position("BTC/USD") is None

    def test_close_position_partial(self) -> None:
        """Test partially closing a position."""
        mgr = PositionManager()
        mgr.open_position("BTC/USD", PositionSide.LONG, Decimal("2"), Decimal("50000"))

        position = mgr.close_position("BTC/USD", Decimal("55000"), Decimal("1"))
        assert position.quantity == Decimal("1")
        assert position.realized_pnl == Decimal("5000")

        # Still have position
        remaining = mgr.get_position("BTC/USD")
        assert remaining is not None
        assert remaining.quantity == Decimal("1")

    def test_short_pnl_calculation(self) -> None:
        """Test P&L for short positions."""
        mgr = PositionManager()
        mgr.open_position("ETH/USD", PositionSide.SHORT, Decimal("10"), Decimal("3000"))

        # Price dropped = profit for short
        closed = mgr.close_position("ETH/USD", Decimal("2800"))
        assert closed.realized_pnl == Decimal("2000")  # (3000 - 2800) * 10

    def test_unrealized_pnl(self) -> None:
        """Test unrealized P&L calculation."""
        mgr = PositionManager()
        position = mgr.open_position("BTC/USD", PositionSide.LONG, Decimal("1"), Decimal("50000"))

        assert position.unrealized_pnl(Decimal("55000")) == Decimal("5000")
        assert position.unrealized_pnl(Decimal("45000")) == Decimal("-5000")

    def test_close_nonexistent_raises(self) -> None:
        """Test closing non-existent position raises."""
        mgr = PositionManager()
        with pytest.raises(ValueError, match="No position"):
            mgr.close_position("BTC/USD", Decimal("50000"))


# ========== EquityCurve Tests ==========


class TestEquityCurve:
    """Tests for EquityCurve."""

    def test_record_and_retrieve(self) -> None:
        """Test recording and retrieving snapshots."""
        from datetime import datetime, timezone

        curve = EquityCurve()

        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            total_equity=Decimal("10000"),
            available_balance=Decimal("10000"),
            reserved_balance=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            position_count=0,
        )
        curve.record(snapshot)

        assert len(curve) == 1
        assert curve.latest == snapshot

    def test_max_drawdown(self) -> None:
        """Test max drawdown calculation."""
        from datetime import datetime, timezone

        curve = EquityCurve()
        now = datetime.now(timezone.utc)

        # Record equity: 10000 -> 12000 -> 9000 -> 11000
        for equity in [10000, 12000, 9000, 11000]:
            curve.record(
                PortfolioSnapshot(
                    timestamp=now,
                    total_equity=Decimal(str(equity)),
                    available_balance=Decimal(str(equity)),
                    reserved_balance=Decimal("0"),
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    position_count=0,
                )
            )

        # Max drawdown: 12000 -> 9000 = 25%
        assert curve.max_drawdown == Decimal("0.25")

    def test_total_return(self) -> None:
        """Test total return calculation."""
        from datetime import datetime, timezone

        curve = EquityCurve()
        now = datetime.now(timezone.utc)

        # 10000 -> 15000 = 50% return
        for equity in [10000, 15000]:
            curve.record(
                PortfolioSnapshot(
                    timestamp=now,
                    total_equity=Decimal(str(equity)),
                    available_balance=Decimal(str(equity)),
                    reserved_balance=Decimal("0"),
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    position_count=0,
                )
            )

        assert curve.total_return() == Decimal("0.5")


# ========== PortfolioManager Tests ==========


class TestPortfolioManager:
    """Tests for PortfolioManager."""

    def test_initial_state(self) -> None:
        """Test initial portfolio state."""
        pm = PortfolioManager()

        assert pm.get_available("USD") == Decimal("10000")
        assert len(pm.get_all_positions()) == 0
        assert pm.get_total_equity() == Decimal("10000")

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = PortfolioConfig(
            quote_currency="USDT",
            initial_balance=Decimal("50000"),
        )
        pm = PortfolioManager(config=config)

        assert pm.quote_currency == "USDT"
        assert pm.get_available("USDT") == Decimal("50000")

    def test_open_long_deducts_balance(self) -> None:
        """Test opening long reserves and settles balance."""
        pm = PortfolioManager()

        pm.open_long("BTC/USD", Decimal("0.1"), Decimal("50000"))

        # Should have deducted 5000 (0.1 * 50000)
        assert pm.get_available("USD") == Decimal("5000")
        assert len(pm.get_all_positions()) == 1

    def test_close_long_with_profit(self) -> None:
        """Test closing long with profit."""

        def price_provider(symbol: str) -> Decimal:
            return Decimal("55000")

        pm = PortfolioManager(price_provider=price_provider)
        pm.open_long("BTC/USD", Decimal("0.1"), Decimal("50000"))

        # Close at 55000
        pm.close_position("BTC/USD", Decimal("55000"))

        # Should have 10000 + 500 profit
        assert pm.get_available("USD") == Decimal("10500")

    def test_close_long_with_loss(self) -> None:
        """Test closing long with loss."""

        def price_provider(symbol: str) -> Decimal:
            return Decimal("45000")

        pm = PortfolioManager(price_provider=price_provider)
        pm.open_long("BTC/USD", Decimal("0.1"), Decimal("50000"))

        # Close at 45000
        pm.close_position("BTC/USD", Decimal("45000"))

        # Should have 10000 - 500 loss
        assert pm.get_available("USD") == Decimal("9500")

    def test_insufficient_balance_raises(self) -> None:
        """Test opening position with insufficient balance."""
        pm = PortfolioManager()

        with pytest.raises(ValueError, match="Insufficient"):
            pm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))  # Need 50k, have 10k

    def test_equity_includes_unrealized_pnl(self) -> None:
        """Test total equity includes unrealized P&L."""

        def price_provider(symbol: str) -> Decimal:
            return Decimal("55000")

        pm = PortfolioManager(price_provider=price_provider)
        pm.open_long("BTC/USD", Decimal("0.1"), Decimal("50000"))

        # Balance: 5000, Position value: 5000, Unrealized: 500
        assert pm.get_total_equity() == Decimal("10500")
        assert pm.get_unrealized_pnl() == Decimal("500")

    def test_snapshot_recorded(self) -> None:
        """Test snapshots are recorded."""
        pm = PortfolioManager()

        # Initial snapshot should exist
        assert len(pm.equity_curve) >= 1

        pm.open_long("BTC/USD", Decimal("0.1"), Decimal("50000"))

        # Trade should trigger snapshot
        assert len(pm.equity_curve) >= 2

    def test_get_summary(self) -> None:
        """Test portfolio summary."""

        def price_provider(symbol: str) -> Decimal:
            return Decimal("55000")

        pm = PortfolioManager(price_provider=price_provider)
        pm.open_long("BTC/USD", Decimal("0.1"), Decimal("50000"))

        summary = pm.get_summary()

        assert summary["quote_currency"] == "USD"
        assert summary["total_equity"] == 10500.0
        assert summary["position_count"] == 1
        assert len(summary["positions"]) == 1
        assert summary["positions"][0]["symbol"] == "BTC/USD"
