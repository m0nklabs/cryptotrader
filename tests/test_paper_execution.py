"""Tests for paper trading execution engine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.execution.order_book import OrderBook
from core.execution.paper import PaperExecutor


# ============================================================================
# OrderBook Tests
# ============================================================================


def test_order_book_add_order():
    """Test adding a limit order to the order book."""
    book = OrderBook()
    order_id = book.add_order("BTCUSD", "BUY", Decimal("1.0"), Decimal("50000"))

    assert order_id == 1
    order = book.get_order(order_id)
    assert order is not None
    assert order.symbol == "BTCUSD"
    assert order.side == "BUY"
    assert order.qty == Decimal("1.0")
    assert order.limit_price == Decimal("50000")


def test_order_book_cancel_order():
    """Test cancelling a limit order."""
    book = OrderBook()
    order_id = book.add_order("BTCUSD", "BUY", Decimal("1.0"), Decimal("50000"))

    assert book.cancel_order(order_id) is True
    assert book.get_order(order_id) is None
    assert book.cancel_order(order_id) is False  # Already cancelled


def test_order_book_check_fills_buy_order():
    """Test that BUY limit orders fill when price drops to/below limit."""
    book = OrderBook()
    book.add_order("BTCUSD", "BUY", Decimal("1.0"), Decimal("50000"))

    # Price above limit - no fill
    fills = book.check_fills("BTCUSD", Decimal("51000"))
    assert len(fills) == 0

    # Price at limit - should fill the first order
    fills = book.check_fills("BTCUSD", Decimal("50000"))
    assert len(fills) == 1
    assert fills[0].qty == Decimal("1.0")

    # Add another order after the first was filled
    book.add_order("BTCUSD", "BUY", Decimal("0.5"), Decimal("50000"))

    # Price at limit again - should fill the second order
    fills = book.check_fills("BTCUSD", Decimal("50000"))
    assert len(fills) == 1
    assert fills[0].qty == Decimal("0.5")


def test_order_book_check_fills_sell_order():
    """Test that SELL limit orders fill when price rises to/above limit."""
    book = OrderBook()
    book.add_order("BTCUSD", "SELL", Decimal("1.0"), Decimal("52000"))

    # Price below limit - no fill
    fills = book.check_fills("BTCUSD", Decimal("51000"))
    assert len(fills) == 0

    # Price at limit - should fill
    fills = book.check_fills("BTCUSD", Decimal("52000"))
    assert len(fills) == 1
    assert fills[0].limit_price == Decimal("52000")


def test_order_book_get_pending_orders():
    """Test retrieving pending orders."""
    book = OrderBook()
    book.add_order("BTCUSD", "BUY", Decimal("1.0"), Decimal("50000"))
    book.add_order("ETHUSD", "SELL", Decimal("2.0"), Decimal("3000"))
    book.add_order("BTCUSD", "SELL", Decimal("0.5"), Decimal("51000"))

    all_orders = book.get_pending_orders()
    assert len(all_orders) == 3

    btc_orders = book.get_pending_orders("BTCUSD")
    assert len(btc_orders) == 2
    assert all(o.symbol == "BTCUSD" for o in btc_orders)


def test_order_book_multiple_symbols():
    """Test order book handles multiple symbols independently."""
    book = OrderBook()
    book.add_order("BTCUSD", "BUY", Decimal("1.0"), Decimal("50000"))
    book.add_order("ETHUSD", "BUY", Decimal("10.0"), Decimal("3000"))

    # Fill only BTC orders
    fills = book.check_fills("BTCUSD", Decimal("49000"))
    assert len(fills) == 1
    assert fills[0].symbol == "BTCUSD"

    # ETH order should still be pending
    eth_orders = book.get_pending_orders("ETHUSD")
    assert len(eth_orders) == 1


# ============================================================================
# PaperExecutor Tests
# ============================================================================


def test_execute_market_order_buy():
    """Test executing a market BUY order."""
    executor = PaperExecutor()

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    assert order.status == "FILLED"
    assert order.fill_price is not None
    # With default 5 bps slippage, BUY should pay more
    assert order.fill_price > Decimal("50000")
    assert order.filled_at is not None


def test_execute_market_order_sell():
    """Test executing a market SELL order."""
    executor = PaperExecutor()

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    assert order.status == "FILLED"
    assert order.fill_price is not None
    # With slippage, SELL should receive less
    assert order.fill_price < Decimal("50000")


def test_execute_market_order_with_custom_slippage():
    """Test market order with custom slippage."""
    executor = PaperExecutor(default_slippage_bps=Decimal("10"))

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
        slippage_bps=Decimal("20"),  # Override default
    )

    assert order.status == "FILLED"
    # 20 bps = 0.2% slippage on BUY = 50000 * 1.002 = 50100
    expected = Decimal("50000") * Decimal("1.002")
    assert order.fill_price == expected


def test_execute_limit_order():
    """Test executing a limit order (should be pending)."""
    executor = PaperExecutor()

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="limit",
        limit_price=Decimal("49000"),
    )

    assert order.status == "PENDING"
    assert order.fill_price is None
    assert order.limit_price == Decimal("49000")


def test_limit_order_requires_limit_price():
    """Test that limit orders require a limit price."""
    executor = PaperExecutor()

    with pytest.raises(ValueError, match="Limit price required"):
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            order_type="limit",
        )


def test_market_order_requires_market_price():
    """Test that market orders require a market price."""
    executor = PaperExecutor()

    with pytest.raises(ValueError, match="Market price required"):
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            order_type="market",
        )


def test_order_quantity_must_be_positive():
    """Test that order quantity must be positive."""
    executor = PaperExecutor()

    with pytest.raises(ValueError, match="Quantity must be positive"):
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("0"),
            order_type="market",
            market_price=Decimal("50000"),
        )


def test_update_market_price_fills_limit_orders():
    """Test that updating market price fills eligible limit orders."""
    executor = PaperExecutor()

    # Place a BUY limit order at 49000
    order1 = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="limit",
        limit_price=Decimal("49000"),
    )

    # Place a SELL limit order at 51000
    order2 = executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("0.5"),
        order_type="limit",
        limit_price=Decimal("51000"),
    )

    # Update price to 49000 - should fill BUY order
    filled = executor.update_market_price("BTCUSD", Decimal("49000"))
    assert len(filled) == 1
    assert filled[0].order_id == order1.order_id
    assert filled[0].status == "FILLED"
    assert filled[0].fill_price == Decimal("49000")

    # Update price to 51000 - should fill SELL order
    filled = executor.update_market_price("BTCUSD", Decimal("51000"))
    assert len(filled) == 1
    assert filled[0].order_id == order2.order_id


def test_position_tracking_new_long_position():
    """Test opening a new long position."""
    executor = PaperExecutor()

    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    position = executor.get_position("BTCUSD")
    assert position is not None
    assert position.qty == Decimal("1.0")
    assert position.avg_entry > Decimal("50000")  # Due to slippage
    assert position.realized_pnl == Decimal("0")


def test_position_tracking_new_short_position():
    """Test opening a new short position."""
    executor = PaperExecutor()

    executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    position = executor.get_position("BTCUSD")
    assert position is not None
    assert position.qty == Decimal("-1.0")  # Negative for short
    assert position.avg_entry < Decimal("50000")  # Due to slippage


def test_position_tracking_add_to_position():
    """Test adding to an existing position."""
    executor = PaperExecutor(default_slippage_bps=Decimal("0"))  # No slippage for easier math

    # First buy
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    # Second buy at different price
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("52000"),
    )

    position = executor.get_position("BTCUSD")
    assert position.qty == Decimal("2.0")
    # Average entry should be (50000 + 52000) / 2 = 51000
    assert position.avg_entry == Decimal("51000")


def test_position_tracking_reduce_position():
    """Test reducing a position (partial close)."""
    executor = PaperExecutor(default_slippage_bps=Decimal("0"))

    # Open position
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("2.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    # Partially close at profit
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("51000"),
    )

    position = executor.get_position("BTCUSD")
    assert position.qty == Decimal("1.0")
    assert position.avg_entry == Decimal("50000")  # Entry price unchanged
    # Realized P&L should be (51000 - 50000) * 1.0 = 1000
    assert position.realized_pnl == Decimal("1000")


def test_position_tracking_close_position():
    """Test fully closing a position."""
    executor = PaperExecutor(default_slippage_bps=Decimal("0"))

    # Open position
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    # Close position
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("52000"),
    )

    position = executor.get_position("BTCUSD")
    assert position.qty == Decimal("0")
    # Realized P&L should be (52000 - 50000) * 1.0 = 2000
    assert position.realized_pnl == Decimal("2000")


def test_position_tracking_flip_position():
    """Test flipping from long to short."""
    executor = PaperExecutor(default_slippage_bps=Decimal("0"))

    # Open long position
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    # Sell more than we have (flip to short)
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("2.0"),
        order_type="market",
        market_price=Decimal("51000"),
    )

    position = executor.get_position("BTCUSD")
    assert position.qty == Decimal("-1.0")  # Now short 1.0
    assert position.avg_entry == Decimal("51000")  # Entry of the new short
    # Realized P&L from closing the long: (51000 - 50000) * 1.0 = 1000
    assert position.realized_pnl == Decimal("1000")


def test_unrealized_pnl_calculation_long():
    """Test unrealized P&L calculation for long position."""
    executor = PaperExecutor(default_slippage_bps=Decimal("0"))

    # Open long position
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    # Price goes up - profit
    unrealized_pnl = executor.get_unrealized_pnl("BTCUSD", Decimal("52000"))
    assert unrealized_pnl == Decimal("2000")

    # Price goes down - loss
    unrealized_pnl = executor.get_unrealized_pnl("BTCUSD", Decimal("49000"))
    assert unrealized_pnl == Decimal("-1000")


def test_unrealized_pnl_calculation_short():
    """Test unrealized P&L calculation for short position."""
    executor = PaperExecutor(default_slippage_bps=Decimal("0"))

    # Open short position
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    # Price goes down - profit for short
    unrealized_pnl = executor.get_unrealized_pnl("BTCUSD", Decimal("49000"))
    assert unrealized_pnl == Decimal("1000")

    # Price goes up - loss for short
    unrealized_pnl = executor.get_unrealized_pnl("BTCUSD", Decimal("51000"))
    assert unrealized_pnl == Decimal("-1000")


def test_unrealized_pnl_no_position():
    """Test unrealized P&L when no position exists."""
    executor = PaperExecutor()

    unrealized_pnl = executor.get_unrealized_pnl("BTCUSD", Decimal("50000"))
    assert unrealized_pnl == Decimal("0")


def test_cancel_order():
    """Test cancelling a pending limit order."""
    executor = PaperExecutor()

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="limit",
        limit_price=Decimal("49000"),
    )

    assert executor.cancel_order(order.order_id) is True

    # Order should be marked as cancelled
    cancelled_order = executor.get_order(order.order_id)
    assert cancelled_order.status == "CANCELLED"

    # Should not fill even when price crosses
    filled = executor.update_market_price("BTCUSD", Decimal("49000"))
    assert len(filled) == 0


def test_cannot_cancel_filled_order():
    """Test that filled orders cannot be cancelled."""
    executor = PaperExecutor()

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    assert executor.cancel_order(order.order_id) is False


def test_get_order():
    """Test retrieving an order by ID."""
    executor = PaperExecutor()

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    retrieved = executor.get_order(order.order_id)
    assert retrieved is not None
    assert retrieved.order_id == order.order_id
    assert retrieved.symbol == "BTCUSD"


def test_complex_trading_scenario():
    """Test a complex trading scenario with multiple orders and positions."""
    executor = PaperExecutor(default_slippage_bps=Decimal("0"))

    # 1. Buy 1 BTC at 50000
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    # 2. Place limit order to buy more at 48000
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="limit",
        limit_price=Decimal("48000"),
    )

    # 3. Price drops, limit order fills
    filled = executor.update_market_price("BTCUSD", Decimal("48000"))
    assert len(filled) == 1

    # Position should now be 2 BTC with avg entry of 49000
    position = executor.get_position("BTCUSD")
    assert position.qty == Decimal("2.0")
    assert position.avg_entry == Decimal("49000")

    # 4. Sell 1 BTC at 51000
    executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("51000"),
    )

    # Position should be 1 BTC with realized profit of 2000
    position = executor.get_position("BTCUSD")
    assert position.qty == Decimal("1.0")
    assert position.realized_pnl == Decimal("2000")

    # Unrealized P&L at 52000 should be (52000 - 49000) * 1.0 = 3000
    unrealized = executor.get_unrealized_pnl("BTCUSD", Decimal("52000"))
    assert unrealized == Decimal("3000")


def test_legacy_executor_compatibility():
    """Test that legacy PaperExecutor.execute() still works."""
    from core.types import OrderIntent

    executor = PaperExecutor()

    order = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("1.0"),
        order_type="market",
    )

    result = executor.execute(order)
    assert result.dry_run is True
    assert result.accepted is True
    assert result.reason == "paper-execution"


def test_get_last_price():
    """Test that update_market_price stores the last price and get_last_price retrieves it."""
    executor = PaperExecutor()

    # Initially no price
    assert executor.get_last_price("BTCUSD") is None

    # Update price
    executor.update_market_price("BTCUSD", Decimal("50000"))
    assert executor.get_last_price("BTCUSD") == Decimal("50000")

    # Update again
    executor.update_market_price("BTCUSD", Decimal("51000"))
    assert executor.get_last_price("BTCUSD") == Decimal("51000")

    # Different symbol remains None
    assert executor.get_last_price("ETHUSD") is None

    # Update second symbol
    executor.update_market_price("ETHUSD", Decimal("3000"))
    assert executor.get_last_price("ETHUSD") == Decimal("3000")
    assert executor.get_last_price("BTCUSD") == Decimal("51000")  # Unchanged
