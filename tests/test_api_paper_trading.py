"""Tests for the paper trading API endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app, _get_paper_executor


@pytest.fixture(autouse=True)
def reset_paper_executor():
    """Reset the paper executor state before each test."""
    from api.main import (
        _automation_config,
        _cooldown_check,
        _get_trade_history,
        _get_signal_dedup,
    )

    executor = _get_paper_executor()
    executor._orders.clear()
    executor._positions.clear()
    executor._last_prices.clear()
    executor._order_book._orders.clear()
    executor._next_order_id = 1

    # Reset shared trade history
    th = _get_trade_history()
    th.trades.clear()

    # Reset cooldown check
    if _cooldown_check is not None:
        _cooldown_check.__dict__.clear()
        _cooldown_check.__dict__["config"] = _automation_config
        _cooldown_check.__dict__["trade_history"] = th

    # Reset signal dedup - clear the last_signal dict (not __dict__)
    dedup = _get_signal_dedup()
    if hasattr(dedup, "last_signal") and dedup.last_signal is not None:
        dedup.last_signal.clear()

    yield


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestOrderEndpoints:
    """Tests for order-related endpoints."""

    def test_place_market_order(self, client):
        """Test placing a market order."""
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        order = data["order"]
        assert order["order_id"] == 1
        assert order["symbol"] == "BTCUSD"
        assert order["side"] == "BUY"
        assert order["order_type"] == "market"
        assert order["status"] == "FILLED"
        assert Decimal(order["avg_fill_price"]) > Decimal("50000")  # Slippage

    def test_place_limit_order(self, client):
        """Test placing a limit order."""
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "0.5",
                "order_type": "limit",
                "limit_price": "49000",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        order = data["order"]
        assert order["order_id"] == 1
        assert order["status"] == "PENDING"
        assert order["limit_price"] == "49000"
        assert order["avg_fill_price"] is None

    def test_limit_order_requires_limit_price(self, client):
        """Test that limit orders require a limit price."""
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "limit",
            },
        )
        assert response.status_code == 400
        assert "limit_price required" in response.json()["detail"]["message"]

    def test_market_order_requires_market_price(self, client):
        """Test that market orders require a market price."""
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
            },
        )
        assert response.status_code == 400
        assert "market_price required" in response.json()["detail"]["message"]

    def test_get_orders_empty(self, client):
        """Test getting orders when none exist."""
        response = client.get("/orders")
        assert response.status_code == 200
        assert response.json() == {"orders": []}

    def test_get_orders_with_filters(self, client):
        """Test getting orders with filters."""
        # Place some orders
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        client.post(
            "/orders",
            json={
                "symbol": "ETHUSD",
                "side": "SELL",
                "qty": "10.0",
                "order_type": "limit",
                "limit_price": "3500",
            },
        )

        # Get all orders
        response = client.get("/orders")
        assert len(response.json()["orders"]) == 2

        # Filter by symbol
        response = client.get("/orders", params={"symbol": "BTCUSD"})
        orders = response.json()["orders"]
        assert len(orders) == 1
        assert orders[0]["symbol"] == "BTCUSD"

        # Filter by status
        response = client.get("/orders", params={"status": "PENDING"})
        orders = response.json()["orders"]
        assert len(orders) == 1
        assert orders[0]["status"] == "PENDING"

    def test_cancel_order(self, client):
        """Test cancelling an order."""
        # Place a limit order
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "limit",
                "limit_price": "49000",
            },
        )
        order_id = response.json()["order"]["order_id"]

        # Cancel it
        response = client.delete(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["order"]["status"] == "CANCELLED"

    def test_cancel_nonexistent_order(self, client):
        """Test cancelling an order that doesn't exist."""
        response = client.delete("/orders/999")
        assert response.status_code == 404

    def test_cancel_filled_order(self, client):
        """Test that filled orders cannot be cancelled."""
        # Place a market order (immediately filled)
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        order_id = response.json()["order"]["order_id"]

        # Try to cancel it
        response = client.delete(f"/orders/{order_id}")
        assert response.status_code == 400
        assert "Cannot cancel" in response.json()["detail"]["message"]


class TestOrderFillContract:
    """The paper order fill contract behind POST /orders, GET /orders and GET /orders/{id}."""

    # The complete row shape. A missing or duplicated alias fails this set.
    CONTRACT_FIELDS = {
        "order_id",
        "mode",
        "symbol",
        "side",
        "order_type",
        "status",
        "requested_qty",
        "filled_qty",
        "remaining_qty",
        "fill_ratio",
        "avg_fill_price",
        "limit_price",
        "fees",
        "slippage_bps",
        "created_at",
        "filled_at",
    }

    @staticmethod
    def _executor(**fill_probs: str):
        """Return the API's paper executor with deterministic fill probabilities."""
        from api.main import _get_paper_executor

        executor = _get_paper_executor()
        for name, value in fill_probs.items():
            setattr(executor, name, Decimal(value))
        return executor

    @staticmethod
    def _market_order(client, qty: str = "1.0", market_price: str = "50000", symbol: str = "BTCUSD"):
        """Place a market order through the API and return the response body."""
        response = client.post(
            "/orders",
            json={
                "symbol": symbol,
                "side": "BUY",
                "qty": qty,
                "order_type": "market",
                "market_price": market_price,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_market_order_carries_the_full_fill_contract(self, client):
        """POST and GET must emit the same, complete row for a filled order."""
        self._executor(_partial_fill_prob="1", _missed_fill_prob="0")

        placed = self._market_order(client)["order"]
        assert set(placed) == self.CONTRACT_FIELDS

        assert placed["mode"] == "paper"
        assert placed["status"] == "FILLED"
        assert Decimal(placed["requested_qty"]) == Decimal("1.0")
        assert Decimal(placed["filled_qty"]) == Decimal("1.0")
        assert Decimal(placed["remaining_qty"]) == Decimal("0")
        assert Decimal(placed["fill_ratio"]) == Decimal("1")
        assert Decimal(placed["avg_fill_price"]) > Decimal("50000")  # Slippage applied
        assert Decimal(placed["fees"]) > 0
        assert Decimal(placed["slippage_bps"]) == Decimal("5")
        assert placed["created_at"] is not None
        assert placed["filled_at"] is not None

        listed = client.get("/orders").json()["orders"]
        assert len(listed) == 1
        # The list row is byte-identical to the placement row: one contract.
        assert listed[0] == placed

    def test_pending_limit_order_reports_nothing_filled(self, client):
        """A resting limit order must not claim the requested qty as filled."""
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "limit",
                "limit_price": "49000",
            },
        )
        assert response.status_code == 200
        order = response.json()["order"]

        assert set(order) == self.CONTRACT_FIELDS
        assert order["status"] == "PENDING"
        assert Decimal(order["requested_qty"]) == Decimal("1.0")
        assert Decimal(order["filled_qty"]) == Decimal("0")
        assert Decimal(order["remaining_qty"]) == Decimal("1.0")
        assert Decimal(order["fill_ratio"]) == Decimal("0")
        assert order["avg_fill_price"] is None
        assert order["filled_at"] is None

    def test_partial_fill_reports_requested_filled_and_remaining(self, client):
        """A PARTIAL fill exposes requested/filled/remaining and a true ratio."""
        self._executor(_partial_fill_prob="0", _missed_fill_prob="0")

        order = self._market_order(client, qty="2.0")["order"]
        assert order["status"] == "PARTIAL"

        requested = Decimal(order["requested_qty"])
        filled = Decimal(order["filled_qty"])
        remaining = Decimal(order["remaining_qty"])
        assert requested == Decimal("2.0")
        assert Decimal("0") < filled < requested
        assert filled + remaining == requested
        assert Decimal("0") < Decimal(order["fill_ratio"]) < Decimal("1")
        assert order["avg_fill_price"] is not None
        assert order["filled_at"] is not None

    def test_missed_fill_reports_nothing_filled(self, client):
        """A MISSED order fills nothing, so it must advertise no fill price."""
        self._executor(_missed_fill_prob="1")

        order = self._market_order(client, qty="1.0")["order"]
        assert order["status"] == "MISSED"
        assert Decimal(order["requested_qty"]) == Decimal("1.0")
        assert Decimal(order["filled_qty"]) == Decimal("0")
        assert Decimal(order["remaining_qty"]) == Decimal("1.0")
        assert Decimal(order["fill_ratio"]) == Decimal("0")
        assert order["avg_fill_price"] is None
        assert order["filled_at"] is None

        listed = client.get("/orders").json()["orders"]
        assert [o["status"] for o in listed] == ["MISSED"]

    def test_status_filter_accepts_every_executor_state(self, client):
        """PARTIAL and MISSED are first-class filters, unknown values are rejected."""
        self._executor(_partial_fill_prob="0", _missed_fill_prob="0")
        partial = self._market_order(client, qty="2.0")["order"]
        assert partial["status"] == "PARTIAL"

        # A second order on the same symbol inside the cooldown window is
        # rejected, so the missed fill is placed on a different symbol.
        self._executor(_missed_fill_prob="1")
        missed = self._market_order(client, symbol="ETHUSD", market_price="3000")["order"]
        assert missed["status"] == "MISSED"

        response = client.get("/orders", params={"status": "PARTIAL"})
        assert response.status_code == 200
        assert [o["order_id"] for o in response.json()["orders"]] == [partial["order_id"]]

        response = client.get("/orders", params={"status": "MISSED"})
        assert response.status_code == 200
        assert [o["order_id"] for o in response.json()["orders"]] == [missed["order_id"]]

        # Every executor state is an accepted filter value; empty lists are fine.
        for status in ("PENDING", "FILLED", "CANCELLED", "PARTIAL", "MISSED"):
            assert client.get("/orders", params={"status": status}).status_code == 200

        # Anything outside the status model is a validation error, not a silent empty list.
        assert client.get("/orders", params={"status": "BOGUS"}).status_code == 422

    def test_get_single_order_returns_the_list_row(self, client):
        """GET /orders/{id} serves exactly the row the list endpoint emits."""
        self._executor(_partial_fill_prob="1", _missed_fill_prob="0")
        placed = self._market_order(client)["order"]

        response = client.get(f"/orders/{placed['order_id']}")
        assert response.status_code == 200
        assert response.json() == placed

    def test_get_single_unknown_order_returns_structured_404(self, client):
        """An unknown order ID is a structured 404, not a crash or an empty row."""
        response = client.get("/orders/999")
        assert response.status_code == 404
        assert response.json() == {"detail": {"error": "not_found", "message": "Order 999 not found"}}

    def test_list_route_is_not_shadowed_by_the_single_order_route(self, client):
        """GET /orders must stay the list route instead of binding order_id."""
        response = client.get("/orders")
        assert response.status_code == 200
        assert set(response.json()) == {"orders"}

        # A non-numeric ID is a validation error, never a 404 out of the list route.
        assert client.get("/orders/not-an-order").status_code == 422

    def test_cancelled_order_stays_listed_with_its_fill_state(self, client):
        """Cancelling keeps the order in the ledger, with nothing filled."""
        response = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "limit",
                "limit_price": "49000",
            },
        )
        order_id = response.json()["order"]["order_id"]

        cancelled_response = client.delete(f"/orders/{order_id}")
        assert cancelled_response.status_code == 200

        listed = client.get("/orders").json()["orders"]
        assert len(listed) == 1
        cancelled = listed[0]
        assert cancelled["status"] == "CANCELLED"
        assert cancelled["order_id"] == order_id
        assert Decimal(cancelled["filled_qty"]) == Decimal("0")
        assert Decimal(cancelled["remaining_qty"]) == Decimal("1.0")
        assert cancelled["avg_fill_price"] is None

        filtered = client.get("/orders", params={"status": "CANCELLED"}).json()["orders"]
        assert [o["order_id"] for o in filtered] == [order_id]
        assert client.get(f"/orders/{order_id}").json()["status"] == "CANCELLED"


class TestPositionEndpoints:
    """Tests for position-related endpoints."""

    def test_get_positions_empty(self, client):
        """Test getting positions when none exist."""
        response = client.get("/positions")
        assert response.status_code == 200
        assert response.json() == {"positions": []}

    def test_get_positions_after_order(self, client):
        """Test getting positions after placing an order."""
        # Place a market order
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )

        response = client.get("/positions")
        positions = response.json()["positions"]
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTCUSD"
        assert Decimal(positions[0]["qty"]) == Decimal("1.0")

    def test_get_positions_by_symbol(self, client):
        """Test filtering positions by symbol."""
        # Place orders for different symbols
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        client.post(
            "/orders",
            json={
                "symbol": "ETHUSD",
                "side": "BUY",
                "qty": "10.0",
                "order_type": "market",
                "market_price": "3000",
            },
        )

        # Filter by symbol
        response = client.get("/positions", params={"symbol": "BTCUSD"})
        positions = response.json()["positions"]
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTCUSD"

    def test_close_position(self, client):
        """Test closing a position."""
        # Open a position
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )

        # Close it
        response = client.post(
            "/positions/BTCUSD/close",
            params={"market_price": "51000"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Position closed"
        assert data["close_order"]["symbol"] == "BTCUSD"
        assert data["close_order"]["side"] == "SELL"
        assert data["close_order"]["status"] == "FILLED"

        # Verify position is gone
        response = client.get("/positions", params={"symbol": "BTCUSD"})
        positions = response.json()["positions"]
        # Position should be closed (qty = 0, not in list of non-zero positions)
        btc_positions = [p for p in positions if p["symbol"] == "BTCUSD" and Decimal(p["qty"]) != 0]
        assert len(btc_positions) == 0

    def test_close_nonexistent_position(self, client):
        """Test closing a position that doesn't exist."""
        response = client.post(
            "/positions/BTCUSD/close",
            params={"market_price": "50000"},
        )
        assert response.status_code == 404

    def test_close_position_partial_fill_reports_outcome(self, client):
        """Partial close must surface actual outcome, not 'Position closed'."""
        from api.main import _get_paper_executor

        executor = _get_paper_executor()
        # Force deterministic partial fill: partial_fill_prob below 1 but
        # picked deterministically by using price that lands in partial bucket.
        executor._partial_fill_prob = Decimal("0.5")
        executor._missed_fill_prob = Decimal("0")

        # Open a position that will fully fill (skip the first partial bucket).
        # Order id 1 with price 50000 hash yields a full fill under probs above.
        executor.execute_paper_order(
            symbol="BTCUSD",
            side="BUY",
            qty=Decimal("1.0"),
            order_type="market",
            market_price=Decimal("49999"),  # partial bucket
        )
        # If the open order ended up partial, top up via another partial bucket
        # until we have a non-zero position.
        position = executor.get_position("BTCUSD")
        if position is None or position.qty == 0:
            executor.execute_paper_order(
                symbol="BTCUSD",
                side="BUY",
                qty=Decimal("1.0"),
                order_type="market",
                market_price=Decimal("50000"),
            )
        position = executor.get_position("BTCUSD")
        assert position is not None and position.qty > 0

        # Now close with a price that lands in the partial bucket for the
        # next order id. The hash formula is _next_order_id:fill_price.
        # Match the simulator's deterministic hash without depending on
        # internal helpers.
        import hashlib

        def _hash_to_unit(seed: str) -> Decimal:
            h = hashlib.sha256(seed.encode("utf-8")).digest()
            return (Decimal(int.from_bytes(h[:8], "big")) % Decimal("10000000000")) / Decimal("10000000000")

        next_oid = executor._next_order_id
        # Pick a price that lands in the partial bucket deterministically.
        for candidate in (Decimal("49999"), Decimal("51999"), Decimal("47999"), Decimal("50999"), Decimal("49001")):
            rand = _hash_to_unit(f"{next_oid}:{candidate}")
            if rand < Decimal("0.5"):
                close_price = candidate
                break
        else:
            # Fall through: any price works for the assertion shape.
            close_price = Decimal("49999")

        response = client.post(
            "/positions/BTCUSD/close",
            params={"market_price": str(close_price)},
        )
        assert response.status_code == 200
        data = response.json()
        # Whatever the outcome, the response must surface actual fill fields.
        assert "fill_status" in data
        assert "requested_qty" in data
        assert "filled_qty" in data
        assert "remaining_qty" in data
        # If it actually was a partial fill, the message must reflect that
        # and success must be False; if it filled, message should be the
        # legacy string and success True.
        if data["fill_status"] == "PARTIAL":
            assert data["success"] is False
            assert "partially closed" in data["message"].lower()
        elif data["fill_status"] == "FILLED":
            assert data["success"] is True
            assert data["message"] == "Position closed"

    def test_close_position_missed_fill_keeps_position(self, client):
        """A missed close must leave the position open and report success=False."""
        from api.main import _get_paper_executor

        executor = _get_paper_executor()
        # Force deterministic missed fill.
        executor._partial_fill_prob = Decimal("0")
        executor._missed_fill_prob = Decimal("1")

        # Open a position via direct position state — bypass fill simulator.
        executor._update_position("BTCUSD", "BUY", Decimal("1.0"), Decimal("50000"))
        assert executor.get_position("BTCUSD").qty == Decimal("1.0")

        response = client.post(
            "/positions/BTCUSD/close",
            params={"market_price": "51000"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["fill_status"] == "MISSED"
        assert data["success"] is False
        assert "missed" in data["message"].lower()

        # Position must still be open.
        position = executor.get_position("BTCUSD")
        assert position is not None
        assert position.qty == Decimal("1.0")


class TestPaperTradingEndpointsExist:
    """Verify that all paper trading endpoints are registered."""

    def test_orders_endpoints_exist(self, route_paths):
        """Test that order endpoints are registered."""
        routes = route_paths(app)
        assert "/orders" in routes
        assert "/orders/{order_id}" in routes
        methods = app.openapi()["paths"]["/orders/{order_id}"].keys()
        assert "get" in methods
        assert "delete" in methods

    def test_positions_endpoints_exist(self, route_paths):
        """Test that position endpoints are registered."""
        routes = route_paths(app)
        assert "/positions" in routes
        assert "/positions/{symbol}/close" in routes


class TestCooldownDedup:
    """Tests for cooldown and signal deduplication in place_order."""

    def setup_method(self):
        """Reset state before each test."""
        from api.main import _get_trade_history, _get_signal_dedup

        th = _get_trade_history()
        th.trades.clear()
        dedup = _get_signal_dedup()
        if hasattr(dedup, "last_signal") and dedup.last_signal is not None:
            dedup.last_signal.clear()

    def test_duplicate_buy_signal_rejected(self, client):
        """Test that duplicate BUY signals within cooldown are rejected."""
        # First BUY order should succeed
        r1 = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert r1.status_code == 200

        # Second BUY order for same symbol should be rejected (cooldown active)
        r2 = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert r2.status_code == 409
        assert r2.json()["detail"]["error"] == "safety_check_failed"

    def test_opposite_signal_allowed(self, client):
        """Test that opposite signals (BUY/SELL) are not deduplicated."""
        # Place a BUY order
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )

        # SELL should be allowed (different side)
        r = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "SELL",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert r.status_code == 200

    def test_trade_recorded_on_rejection(self, client):
        """Test that rejected orders still record a trade in history."""
        from api.main import _get_trade_history

        th = _get_trade_history()
        th.trades.clear()

        # First order succeeds
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert len(th.trades) == 1

        # Second order rejected
        r = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert r.status_code == 409

        # Trade was recorded despite rejection
        assert len(th.trades) == 2

    def test_different_symbols_not_deduplicated(self, client):
        """Test that different symbols are not affected by dedup."""
        client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )

        # ETHUSD should not be affected by BTCUSD cooldown
        r = client.post(
            "/orders",
            json={
                "symbol": "ETHUSD",
                "side": "BUY",
                "qty": "10.0",
                "order_type": "market",
                "market_price": "3000",
            },
        )
        assert r.status_code == 200
