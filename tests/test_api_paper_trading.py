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
        assert Decimal(order["fill_price"]) > Decimal("50000")  # Slippage

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
        assert order["fill_price"] is None

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


class TestPaperTradingEndpointsExist:
    """Verify that all paper trading endpoints are registered."""

    def test_orders_endpoints_exist(self):
        """Test that order endpoints are registered."""
        routes = [route.path for route in app.routes]
        assert "/orders" in routes
        assert "/orders/{order_id}" in routes

    def test_positions_endpoints_exist(self):
        """Test that position endpoints are registered."""
        routes = [route.path for route in app.routes]
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

    def test_unified_cooldown_dedup_path(self, client):
        """Test that CooldownCheck and SignalDeduplication share state correctly.

        When the CooldownCheck reference is wired into SignalDeduplication,
        both mechanisms agree on cooldown boundaries. This prevents signals
        from slipping through when they should be deduplicated.
        """
        from api.main import _get_cooldown_check, _get_signal_dedup
        from core.types import OrderIntent

        # Verify the unified path is active
        dedup = _get_signal_dedup()
        assert dedup.cooldown_check is not None, "CooldownCheck should be wired into SignalDeduplication"

        # First BUY succeeds
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

        # Second BUY should be deduplicated (same side, within cooldown)
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

        # Verify both CooldownCheck and SignalDeduplication agree
        cooldown = _get_cooldown_check()
        cooldown_result = cooldown.check(
            intent=OrderIntent(symbol="BTCUSD", side="BUY", exchange="paper", amount=Decimal("1"))
        )
        assert not cooldown_result.ok, "CooldownCheck should say cooldown is active"

        # SELL should pass through (different side)
        r3 = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "SELL",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert r3.status_code == 200

        # Third BUY should pass through (after SELL updated tracking)
        r4 = client.post(
            "/orders",
            json={
                "symbol": "BTCUSD",
                "side": "BUY",
                "qty": "1.0",
                "order_type": "market",
                "market_price": "50000",
            },
        )
        assert r4.status_code == 200
