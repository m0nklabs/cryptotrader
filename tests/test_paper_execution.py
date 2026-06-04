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


def test_transfer_fee_in_market_order():
  """Test that transfer fees are included in market orders."""
  executor = PaperExecutor()

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      currency="BTC",
  )

  # Transfer fee for BTC withdrawal is 0.0004
  assert order.transfer_fee > Decimal("0")
  assert order.transfer_fee == Decimal("0.0004")


def test_transfer_fee_in_limit_order():
  """Test that transfer fees are included in limit orders."""
  executor = PaperExecutor()

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="limit",
      limit_price=Decimal("49000"),
      currency="BTC",
  )

  assert order.transfer_fee > Decimal("0")
  assert order.transfer_fee == Decimal("0.0004")


def test_funding_fee_in_market_order():
  """Test that funding fees are included in market orders."""
  executor = PaperExecutor()

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      days_held=Decimal("30"),
  )

  # Funding fee = notional * (annual_rate / 365 * days_held)
  # = 50000 * (0.05 / 365 * 30) = 50000 * 0.004109... = ~205.48
  assert order.funding_fee > Decimal("0")


def test_funding_fee_in_limit_order():
  """Test that funding fees are included in limit orders."""
  executor = PaperExecutor()

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="limit",
      limit_price=Decimal("49000"),
      days_held=Decimal("30"),
  )

  assert order.funding_fee > Decimal("0")


def test_custom_transfer_fee():
  """Test that custom transfer fee overrides model."""
  executor = PaperExecutor()

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      transfer_fee=Decimal("1.50"),
  )

  assert order.transfer_fee == Decimal("1.50")


def test_custom_funding_fee():
  """Test that custom funding fee overrides model."""
  executor = PaperExecutor()

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      funding_fee=Decimal("25.00"),
  )

  assert order.funding_fee == Decimal("25.00")


def test_all_fee_types_in_order():
  """Test that trading fees, transfer fees, and funding fees are all present."""
  executor = PaperExecutor()

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      transfer_fee=Decimal("1.50"),
      funding_fee=Decimal("25.00"),
  )

  # Trading fees (maker/taker + spread + slippage)
  assert order.fees > Decimal("0")
  # Transfer fee
  assert order.transfer_fee == Decimal("1.50")
  # Funding fee
  assert order.funding_fee == Decimal("25.00")


def test_total_fees_tracking():
  """Test that total fees track transfer and funding fees."""
  executor = PaperExecutor()

  # First order with default fees
  order1 = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      currency="BTC",
  )

  total1 = executor.get_total_fees()
  transfer1 = executor.get_total_transfer_fees()
  funding1 = executor.get_total_funding_fees()

  assert total1 > Decimal("0")
  assert transfer1 > Decimal("0")
  assert funding1 > Decimal("0")

  # Second order with custom fees
  order2 = executor.execute_paper_order(
      symbol="BTCUSD",
      side="SELL",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("51000"),
      transfer_fee=Decimal("2.00"),
      funding_fee=Decimal("30.00"),
  )

  total2 = executor.get_total_fees()
  transfer2 = executor.get_total_transfer_fees()
  funding2 = executor.get_total_funding_fees()

  # Totals should be higher after second order
  assert total2 > total1
  assert transfer2 > transfer1
  assert funding2 > funding1


def test_fee_models_accessible():
  """Test that fee models are accessible via getter methods."""
  executor = PaperExecutor()

  assert executor.get_transfer_fee_model() is not None
  assert executor.get_funding_rate_model() is not None
  assert executor.get_fee_model() is not None


def test_paper_summary_includes_fees():
  """Test that paper summary includes transfer and funding fee info."""
  executor = PaperExecutor()

  executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      currency="BTC",
  )

  summary = executor.get_paper_summary()

  assert "total_transfer_fees" in summary
  assert "total_funding_fees" in summary
  assert "transfer_fee_model" in summary
  assert "funding_rate_model" in summary
  assert summary["total_transfer_fees"] > 0
  assert summary["total_funding_fees"] > 0


def test_different_currency_transfer_fees():
  """Test that different currencies have different transfer fees."""
  executor = PaperExecutor()

  btc_order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      currency="BTC",
  )

  eth_order = executor.execute_paper_order(
      symbol="ETHUSD",
      side="BUY",
      qty=Decimal("10.0"),
      order_type="market",
      market_price=Decimal("3000"),
      currency="ETH",
  )

  usdt_order = executor.execute_paper_order(
      symbol="USDTUSD",
      side="BUY",
      qty=Decimal("1000.0"),
      order_type="market",
      market_price=Decimal("1.0"),
      currency="USDT",
  )

  # BTC withdrawal: 0.0004, ETH: 0.00135, USDT: 1.8
  assert btc_order.transfer_fee == Decimal("0.0004")
  assert eth_order.transfer_fee == Decimal("0.00135")
  assert usdt_order.transfer_fee == Decimal("1.8")


def test_days_held_affects_funding_fee():
  """Test that days_held parameter affects funding fee calculation."""
  executor = PaperExecutor()

  order_1day = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      days_held=Decimal("1"),
  )

  order_30day = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      days_held=Decimal("30"),
  )

  # 30-day funding fee should be ~30x the 1-day fee
  assert order_30day.funding_fee > order_1day.funding_fee
  assert order_30day.funding_fee > order_1day.funding_fee * Decimal("25")


def test_fees_zero_when_no_fill():
  """Test that fees are still calculated even when fill is missed."""
  executor = PaperExecutor(
      partial_fill_prob=Decimal("0"),  # No partial fills
      missed_fill_prob=Decimal("1.0"),  # Always missed
  )

  order = executor.execute_paper_order(
      symbol="BTCUSD",
      side="BUY",
      qty=Decimal("1.0"),
      order_type="market",
      market_price=Decimal("50000"),
      currency="BTC",
  )

  # Even missed orders should have transfer and funding fees
  assert order.transfer_fee > Decimal("0")
  assert order.funding_fee > Decimal("0")
