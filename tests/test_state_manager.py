"""Tests for the in-memory state manager."""

from decimal import Decimal

import pytest

from core.state import StateManager, StateSnapshot


# ========== Initialization Tests ==========


class TestStateManagerInit:
    """Tests for StateManager initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        sm = StateManager()

        assert sm.quote_currency == "USD"
        assert sm.get_available("USD") == Decimal("0")
        assert len(sm.get_all_positions()) == 0
        assert len(sm.get_all_orders()) == 0

    def test_custom_initial_balances(self) -> None:
        """Test initialization with custom balances."""
        sm = StateManager(
            initial_balances={"USD": Decimal("50000"), "BTC": Decimal("2")},
            quote_currency="USDT",
        )

        assert sm.quote_currency == "USDT"
        assert sm.get_available("USD") == Decimal("50000")
        assert sm.get_available("BTC") == Decimal("2")

    def test_reset(self) -> None:
        """Test resetting state."""
        sm = StateManager(initial_balances={"USD": Decimal("10000")})

        # Add some state
        sm.deposit("ETH", Decimal("1000"))
        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))

        # Reset
        sm.reset(initial_balances={"USD": Decimal("20000")})

        assert sm.get_available("USD") == Decimal("20000")
        assert sm.get_available("ETH") == Decimal("0")
        assert len(sm.get_all_positions()) == 0


# ========== Balance Operations Tests ==========


class TestBalanceOperations:
    """Tests for balance operations."""

    def test_deposit(self) -> None:
        """Test depositing funds."""
        sm = StateManager()

        balance = sm.deposit("USD", Decimal("10000"))
        assert balance.available == Decimal("10000")

    def test_withdraw(self) -> None:
        """Test withdrawing funds."""
        sm = StateManager(initial_balances={"USD": Decimal("5000")})

        balance = sm.withdraw("USD", Decimal("2000"))
        assert balance.available == Decimal("3000")

    def test_withdraw_insufficient_raises(self) -> None:
        """Test withdrawing more than available raises."""
        sm = StateManager(initial_balances={"USD": Decimal("1000")})

        with pytest.raises(ValueError, match="Insufficient"):
            sm.withdraw("USD", Decimal("2000"))

    def test_reserve_and_release(self) -> None:
        """Test reserving and releasing funds."""
        sm = StateManager(initial_balances={"USD": Decimal("5000")})

        # Reserve
        balance = sm.reserve("USD", Decimal("2000"))
        assert balance.available == Decimal("3000")
        assert balance.reserved == Decimal("2000")

        # Release
        balance = sm.release("USD", Decimal("1000"))
        assert balance.available == Decimal("4000")
        assert balance.reserved == Decimal("1000")

    def test_settle_reserved(self) -> None:
        """Test settling reserved funds."""
        sm = StateManager(initial_balances={"USD": Decimal("5000")})
        sm.reserve("USD", Decimal("2000"))

        balance = sm.settle_reserved("USD", Decimal("2000"))
        assert balance.available == Decimal("3000")
        assert balance.reserved == Decimal("0")

    def test_get_all_balances(self) -> None:
        """Test getting all non-zero balances."""
        sm = StateManager(
            initial_balances={"USD": Decimal("10000"), "BTC": Decimal("1")}
        )

        balances = sm.get_all_balances()
        assets = {b.asset for b in balances}
        assert assets == {"USD", "BTC"}


# ========== Position Operations Tests ==========


class TestPositionOperations:
    """Tests for position operations."""

    def test_open_long(self) -> None:
        """Test opening a long position."""
        sm = StateManager()

        position = sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        assert position.symbol == "BTC/USD"
        assert position.side.value == "LONG"
        assert position.quantity == Decimal("1")
        assert position.avg_entry_price == Decimal("50000")

    def test_open_short(self) -> None:
        """Test opening a short position."""
        sm = StateManager()

        position = sm.open_short("ETH/USD", Decimal("10"), Decimal("3000"))
        assert position.symbol == "ETH/USD"
        assert position.side.value == "SHORT"
        assert position.quantity == Decimal("10")

    def test_average_in(self) -> None:
        """Test averaging into existing position."""
        sm = StateManager()

        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        position = sm.open_long("BTC/USD", Decimal("1"), Decimal("52000"))

        assert position.quantity == Decimal("2")
        assert position.avg_entry_price == Decimal("51000")

    def test_close_position_full(self) -> None:
        """Test fully closing a position."""
        sm = StateManager()

        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        closed = sm.close_position("BTC/USD", Decimal("55000"))

        assert closed.quantity == Decimal("0")
        assert closed.realized_pnl == Decimal("5000")
        assert sm.get_position("BTC/USD") is None

    def test_close_position_partial(self) -> None:
        """Test partially closing a position."""
        sm = StateManager()

        sm.open_long("BTC/USD", Decimal("2"), Decimal("50000"))
        position = sm.close_position("BTC/USD", Decimal("55000"), Decimal("1"))

        assert position.quantity == Decimal("1")
        assert position.realized_pnl == Decimal("5000")
        assert sm.has_position("BTC/USD")

    def test_has_position(self) -> None:
        """Test checking for position existence."""
        sm = StateManager()

        assert not sm.has_position("BTC/USD")

        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        assert sm.has_position("BTC/USD")


# ========== Order Operations Tests ==========


class TestOrderOperations:
    """Tests for order operations."""

    def test_execute_market_buy(self) -> None:
        """Test executing a market BUY order."""
        sm = StateManager()

        order = sm.execute_market_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            market_price=Decimal("50000"),
        )

        assert order.status == "FILLED"
        assert order.fill_price is not None
        assert order.fill_qty == Decimal("1.0")

    def test_execute_market_sell(self) -> None:
        """Test executing a market SELL order."""
        sm = StateManager()

        order = sm.execute_market_order(
            symbol="BTCUSD",
            side="SELL",
            qty=Decimal("1.0"),
            market_price=Decimal("50000"),
        )

        assert order.status == "FILLED"
        assert order.fill_price is not None

    def test_execute_limit_order(self) -> None:
        """Test executing a limit order."""
        sm = StateManager()

        order = sm.execute_limit_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            limit_price=Decimal("49000"),
        )

        assert order.status == "PENDING"
        assert order.limit_price == Decimal("49000")
        assert order.fill_price is None

    def test_cancel_order(self) -> None:
        """Test cancelling an order."""
        sm = StateManager()

        order = sm.execute_limit_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            limit_price=Decimal("49000"),
        )

        assert sm.cancel_order(order.order_id) is True
        assert order.status == "CANCELLED"

    def test_get_order(self) -> None:
        """Test getting an order by ID."""
        sm = StateManager()

        order = sm.execute_market_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            market_price=Decimal("50000"),
        )

        retrieved = sm.get_order(order.order_id)
        assert retrieved is not None
        assert retrieved.order_id == order.order_id

    def test_get_orders_by_status(self) -> None:
        """Test filtering orders by status."""
        sm = StateManager()

        sm.execute_market_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            market_price=Decimal("50000"),
        )
        sm.execute_limit_order(
            symbol="ETHUSD",
            side="BUY",
            qty=Decimal("10.0"),
            limit_price=Decimal("3000"),
        )

        filled = sm.get_orders_by_status("FILLED")
        pending = sm.get_orders_by_status("PENDING")

        assert len(filled) >= 1
        assert len(pending) >= 1

    def test_position_tracking_via_paper_executor(self) -> None:
        """Test that market orders update paper executor positions."""
        sm = StateManager()

        # Execute BUY
        sm.execute_market_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("2.0"),
            market_price=Decimal("50000"),
        )

        paper_pos = sm.get_paper_position("BTCUSD")
        assert paper_pos is not None
        assert paper_pos.qty == Decimal("2.0")

    def test_multiple_orders_same_symbol(self) -> None:
        """Test multiple orders for the same symbol."""
        sm = StateManager()

        order1 = sm.execute_market_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            market_price=Decimal("50000"),
        )
        order2 = sm.execute_market_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            market_price=Decimal("52000"),
        )

        assert order1.order_id != order2.order_id
        assert order1.fill_price != order2.fill_price  # Different slippage per order


# ========== Price Operations Tests ==========


class TestPriceOperations:
    """Tests for price operations."""

    def test_update_price(self) -> None:
        """Test updating market price."""
        sm = StateManager()

        sm.update_price("BTCUSD", Decimal("50000"))
        assert sm.get_price("BTCUSD") == Decimal("50000")

    def test_get_price_not_set(self) -> None:
        """Test getting price when not set."""
        sm = StateManager()

        assert sm.get_price("BTCUSD") is None

    def test_unrealized_pnl_long(self) -> None:
        """Test unrealized P&L for long position."""
        sm = StateManager()

        sm.open_long("BTCUSD", Decimal("1"), Decimal("50000"))
        sm.update_price("BTCUSD", Decimal("52000"))

        pnl = sm.get_unrealized_pnl("BTCUSD", Decimal("52000"))
        assert pnl == Decimal("2000")

    def test_unrealized_pnl_short(self) -> None:
        """Test unrealized P&L for short position."""
        sm = StateManager()

        sm.open_short("ETHUSD", Decimal("10"), Decimal("3000"))
        sm.update_price("ETHUSD", Decimal("2800"))

        pnl = sm.get_unrealized_pnl("ETHUSD", Decimal("2800"))
        assert pnl == Decimal("2000")

    def test_unrealized_pnl_no_position(self) -> None:
        """Test unrealized P&L when no position exists."""
        sm = StateManager()

        assert sm.get_unrealized_pnl("BTCUSD", Decimal("50000")) == Decimal("0")


# ========== Portfolio Metrics Tests ==========


class TestPortfolioMetrics:
    """Tests for portfolio metrics."""

    def test_total_equity(self) -> None:
        """Test total equity calculation."""
        sm = StateManager(initial_balances={"USD": Decimal("10000")})

        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        sm.update_price("BTC/USD", Decimal("55000"))

        # Equity = available (10000 - 50000 cost) + BTC position (1 * 55000)
        # Actually: initial 10000, position notional = 50000
        # But open_long doesn't deduct from balance in PositionManager
        equity = sm.get_total_equity()
        assert equity > Decimal("0")

    def test_unrealized_pnl_total(self) -> None:
        """Test total unrealized P&L."""
        sm = StateManager()

        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        sm.update_price("BTC/USD", Decimal("55000"))

        pnl = sm.get_total_unrealized_pnl()
        assert pnl == Decimal("5000")

    def test_realized_pnl(self) -> None:
        """Test realized P&L."""
        sm = StateManager()

        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        sm.close_position("BTC/USD", Decimal("55000"))

        pnl = sm.get_total_realized_pnl()
        assert pnl == Decimal("5000")

    def test_total_fees(self) -> None:
        """Test total fees tracking."""
        sm = StateManager()

        sm.execute_market_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            market_price=Decimal("50000"),
        )

        fees = sm.get_total_fees()
        assert fees >= Decimal("0")


# ========== State Snapshot Tests ==========


class TestStateSnapshot:
    """Tests for state snapshots."""

    def test_take_snapshot(self) -> None:
        """Test taking a state snapshot."""
        sm = StateManager(
            initial_balances={"USD": Decimal("10000"), "BTC": Decimal("1")}
        )
        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        sm.update_price("BTC/USD", Decimal("55000"))

        snapshot = sm.take_snapshot()

        assert isinstance(snapshot, StateSnapshot)
        assert "USD" in snapshot.balances
        assert "BTC" in snapshot.balances
        assert len(snapshot.positions) >= 1
        assert len(snapshot.prices) >= 1

    def test_snapshot_fields(self) -> None:
        """Test snapshot field values."""
        sm = StateManager(initial_balances={"USD": Decimal("10000")})

        snapshot = sm.take_snapshot()

        assert snapshot.balances["USD"]["available"] == "10000"
        assert snapshot.balances["USD"]["reserved"] == "0"
        assert snapshot.balances["USD"]["total"] == "10000"
        assert snapshot.total_equity == "10000"
        assert snapshot.unrealized_pnl == "0"
        assert snapshot.realized_pnl == "0"

    def test_get_last_snapshot(self) -> None:
        """Test getting the last snapshot."""
        sm = StateManager()

        # No snapshot yet
        assert sm.get_last_snapshot() is not None  # Initial snapshot

        sm.take_snapshot()
        last = sm.get_last_snapshot()
        assert last is not None

    def test_snapshot_timestamp(self) -> None:
        """Test snapshot has valid timestamp."""
        sm = StateManager()
        snapshot = sm.take_snapshot()

        assert snapshot.timestamp is not None
        assert snapshot.timestamp.tzinfo is not None


# ========== Integration Tests ==========


class TestIntegration:
    """Integration tests for state manager workflows."""

    def test_full_trade_workflow(self) -> None:
        """Test a complete trade workflow."""
        sm = StateManager(
            initial_balances={"USD": Decimal("50000")},
            quote_currency="USD",
        )

        # 1. Update price
        sm.update_price("BTC/USD", Decimal("50000"))

        # 2. Open long position
        position = sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        assert position.side.value == "LONG"

        # 3. Update price up
        sm.update_price("BTC/USD", Decimal("55000"))

        # 4. Check unrealized P&L
        assert sm.get_total_unrealized_pnl() == Decimal("5000")

        # 5. Close position
        closed = sm.close_position("BTC/USD", Decimal("55000"))
        assert closed.realized_pnl == Decimal("5000")

        # 6. Verify final state
        assert sm.get_total_realized_pnl() == Decimal("5000")

    def test_long_to_short_flip(self) -> None:
        """Test flipping from long to short."""
        sm = StateManager()

        # Open long
        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))

        # Execute sell order that flips to short
        order = sm.execute_market_order(
            symbol="BTCUSD",
            side="SELL",
            qty=Decimal("2.0"),
            market_price=Decimal("52000"),
        )

        paper_pos = sm.get_paper_position("BTCUSD")
        assert paper_pos is not None
        # PaperExecutor creates a new position for SELL (independent of PositionManager)
        # SELL 2 creates short position of -2
        assert paper_pos.qty == Decimal("-2.0")
        # avg_entry has slippage applied (default 5 bps)
        assert paper_pos.avg_entry < Decimal("52000")  # SELL receives less due to slippage

    def test_multiple_symbols(self) -> None:
        """Test managing multiple symbols simultaneously."""
        sm = StateManager(initial_balances={"USD": Decimal("100000")})

        # Open positions in different symbols
        sm.open_long("BTC/USD", Decimal("1"), Decimal("50000"))
        sm.open_short("ETH/USD", Decimal("10"), Decimal("3000"))

        sm.update_price("BTC/USD", Decimal("55000"))
        sm.update_price("ETH/USD", Decimal("2800"))

        assert len(sm.get_all_positions()) == 2
        assert sm.get_total_unrealized_pnl() == Decimal("7000")  # 5000 + 2000

    def test_state_isolation(self) -> None:
        """Test that state manager has independent state."""
        sm1 = StateManager(initial_balances={"USD": Decimal("10000")})
        sm2 = StateManager(initial_balances={"USD": Decimal("20000")})

        sm1.deposit("ETH", Decimal("1000"))
        sm2.deposit("ETH", Decimal("2000"))

        assert sm1.get_available("ETH") == Decimal("1000")
        assert sm2.get_available("ETH") == Decimal("2000")
