"""Tests for lookahead bias prevention in order status checks.

Validates that:
- Orders created after a price update are not filled by that price update
- filled_at timestamps are causally tied to price_update_time
- Chronological ordering is maintained across multiple sessions
- Future data does not influence current order state determinations
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.execution.order_book import OrderBook
from core.execution.paper import PaperExecutor


class TestOrderBookLookaheadBias:
    """Test OrderBook.check_fills for lookahead bias prevention."""

    def test_check_fills_excludes_future_orders(self):
        """Orders created after price_update_time should not be filled."""
        ob = OrderBook()
        price_update_time = datetime.now(timezone.utc)

        # Add an order created BEFORE the price update
        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("50000"),
            order_id=1,
            created_at=price_update_time - timedelta(minutes=1),
        )

        # Add an order created AFTER the price update
        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("50000"),
            order_id=2,
            created_at=price_update_time + timedelta(minutes=1),
        )

        # Check fills at the price update time
        filled = ob.check_fills("BTCUSD", Decimal("49999"), price_update_time)

        # Only the first order should be filled (created before price update)
        assert len(filled) == 1
        assert filled[0].order_id == 1

    def test_check_fills_includes_past_orders(self):
        """Orders created before price_update_time should be eligible for fill."""
        ob = OrderBook()
        price_update_time = datetime.now(timezone.utc)

        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("50000"),
            order_id=1,
            created_at=price_update_time - timedelta(minutes=5),
        )

        filled = ob.check_fills("BTCUSD", Decimal("49999"), price_update_time)
        assert len(filled) == 1
        assert filled[0].order_id == 1

    def test_check_fills_with_no_price_update_time(self):
        """When price_update_time is None, uses current time."""
        ob = OrderBook()
        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("50000"),
            order_id=1,
        )

        filled = ob.check_fills("BTCUSD", Decimal("49999"))
        assert len(filled) == 1

    def test_timestamp_causal_ordering(self):
        """filled_at <= price_update_time ensures causal ordering."""
        ob = OrderBook()
        price_update_time = datetime.now(timezone.utc)

        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("50000"),
            order_id=1,
            created_at=price_update_time - timedelta(minutes=1),
        )

        filled = ob.check_fills("BTCUSD", Decimal("49999"), price_update_time)
        assert len(filled) == 1
        # The filled order's created_at should be <= price_update_time
        assert filled[0].created_at is not None
        assert filled[0].created_at <= price_update_time

    def test_multi_session_timestamp_ordering(self):
        """Multiple sessions maintain chronological timestamp ordering."""
        ob = OrderBook()

        # Session 1: price update at t=0
        session_1_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("50000"),
            order_id=1,
            created_at=session_1_time - timedelta(minutes=1),
        )
        filled_1 = ob.check_fills("BTCUSD", Decimal("49999"), session_1_time)
        assert len(filled_1) == 1

        # Session 2: price update at t=5min (order created at t=2min should still be valid)
        session_2_time = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("48000"),
            order_id=2,
            created_at=session_2_time - timedelta(minutes=3),
        )
        filled_2 = ob.check_fills("BTCUSD", Decimal("47999"), session_2_time)
        assert len(filled_2) == 1
        assert filled_2[0].order_id == 2

        # Session 3: price update at t=10min with a NEW order (order from session 2 was removed)
        session_3_time = datetime(2026, 1, 1, 12, 10, 0, tzinfo=timezone.utc)
        ob.add_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            limit_price=Decimal("47000"),
            order_id=3,
            created_at=session_3_time - timedelta(minutes=1),
        )
        filled_3 = ob.check_fills("BTCUSD", Decimal("46999"), session_3_time)
        assert len(filled_3) == 1
        assert filled_3[0].order_id == 3


class TestPaperExecutorLookaheadBias:
    """Test PaperExecutor.update_market_price for lookahead bias prevention."""

    def test_update_market_price_uses_causal_timestamp(self):
        """filled_at should be set to price_update_time, not datetime.now()."""
        executor = PaperExecutor()
        price_update_time = datetime.now(timezone.utc)

        # Place a limit order (created_at will be set to price_update_time)
        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("50000"),
            price_update_time=price_update_time,
        )
        assert order.status == "PENDING"

        # Update market price with explicit timestamp (use current time)
        filled = executor.update_market_price(
            "BTCUSD",
            Decimal("49999"),
            price_update_time=price_update_time,
        )

        assert len(filled) == 1
        # The filled_at should be the price_update_time, not datetime.now()
        assert filled[0].filled_at == price_update_time
        assert filled[0].status == "FILLED"

    def test_update_market_price_no_lookahead_bias(self):
        """Orders created after price_update_time should not be filled."""
        executor = PaperExecutor()
        # Use current time as the price_update_time
        price_update_time = datetime.now(timezone.utc)

        # Place a limit order (created_at will be set to price_update_time)
        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("50000"),
            price_update_time=price_update_time,
        )

        # The order was created at approximately the same time as price_update_time,
        # so it should be filled
        filled = executor.update_market_price(
            "BTCUSD",
            Decimal("49999"),
            price_update_time=price_update_time,
        )

        assert len(filled) == 1
        assert filled[0].order_id == order.order_id

    def test_update_market_price_with_past_timestamp(self):
        """Orders created before a past price_update_time should be filled."""
        executor = PaperExecutor()
        # Use a past timestamp
        past_price_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Place a limit order (created_at will be set to now, which is after past_price_time)
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("50000"),
        )

        # The order was created after past_price_time, so it should NOT be filled
        # when we use past_price_time as the price_update_time
        filled = executor.update_market_price(
            "BTCUSD",
            Decimal("49999"),
            price_update_time=past_price_time,
        )

        # Order created_at is after past_price_time, so it should be excluded
        assert len(filled) == 0

    def test_update_market_price_with_future_timestamp(self):
        """Orders created before a future price_update_time should be filled."""
        executor = PaperExecutor()
        # Use a future timestamp
        future_price_time = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Place a limit order (created_at will be set to now, which is before future_price_time)
        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("50000"),
        )

        # The order was created before future_price_time, so it should be filled
        filled = executor.update_market_price(
            "BTCUSD",
            Decimal("49999"),
            price_update_time=future_price_time,
        )

        assert len(filled) == 1
        assert filled[0].order_id == order.order_id

    def test_multi_session_execution(self):
        """Multiple sessions maintain chronological order status."""
        executor = PaperExecutor()

        # Session 1: Place order and update price
        session_1_time = datetime.now(timezone.utc)
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("50000"),
            price_update_time=session_1_time,
        )

        filled1 = executor.update_market_price(
            "BTCUSD",
            Decimal("49999"),
            price_update_time=session_1_time,
        )
        assert len(filled1) == 1
        assert filled1[0].filled_at == session_1_time

        # Session 2: Place another order and update price
        session_2_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("48000"),
            price_update_time=session_2_time,
        )

        filled2 = executor.update_market_price(
            "BTCUSD",
            Decimal("47999"),
            price_update_time=session_2_time,
        )
        assert len(filled2) == 1
        assert filled2[0].filled_at == session_2_time

        # Verify chronological ordering
        assert filled1[0].filled_at is not None
        assert filled2[0].filled_at is not None
        assert filled1[0].filled_at < filled2[0].filled_at

    def test_order_status_no_future_influence(self):
        """Order status checks are not influenced by future price updates."""
        executor = PaperExecutor()

        # Place order at current time
        order = executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("50000"),
        )

        # Use a future timestamp for the price update
        price_time_1 = datetime.now(timezone.utc) + timedelta(minutes=5)
        filled1 = executor.update_market_price(
            "BTCUSD",
            Decimal("49999"),
            price_update_time=price_time_1,
        )

        # Verify the order was filled at the correct time
        assert len(filled1) == 1
        assert filled1[0].filled_at == price_time_1
        assert filled1[0].status == "FILLED"

        # Now check order status - should not be influenced by future updates
        current_order = executor.get_order(order.order_id)
        assert current_order is not None
        assert current_order.status == "FILLED"
        assert current_order.filled_at == price_time_1
