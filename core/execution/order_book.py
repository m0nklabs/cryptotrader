from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass
class LimitOrder:
    """Represents a limit order in the order book."""

    order_id: int
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: Decimal
    limit_price: Decimal


class OrderBook:
    """In-memory order book for paper trading limit orders.
    
    Manages pending limit orders and checks for fills when price updates occur.
    """

    def __init__(self) -> None:
        self._orders: dict[int, LimitOrder] = {}
        self._next_order_id = 1

    def add_order(self, symbol: str, side: Literal["BUY", "SELL"], qty: Decimal, limit_price: Decimal, order_id: int | None = None) -> int:
        """Add a limit order to the book.
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            qty: Order quantity
            limit_price: Limit price for the order
            order_id: Optional order ID to use (if None, auto-generate)
            
        Returns:
            order_id: Unique order ID
        """
        if order_id is None:
            order_id = self._next_order_id
            self._next_order_id += 1
        else:
            # Update next_order_id if provided ID is >= current
            if order_id >= self._next_order_id:
                self._next_order_id = order_id + 1
        
        order = LimitOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            limit_price=limit_price,
        )
        self._orders[order_id] = order
        return order_id

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a pending limit order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if order was cancelled, False if not found
        """
        if order_id in self._orders:
            del self._orders[order_id]
            return True
        return False

    def check_fills(self, symbol: str, price: Decimal) -> list[LimitOrder]:
        """Check which limit orders should be filled at the given price.
        
        Args:
            symbol: Trading symbol
            price: Current market price
            
        Returns:
            List of orders that should be filled
        """
        filled_orders = []
        orders_to_remove = []
        
        for order_id, order in self._orders.items():
            if order.symbol != symbol:
                continue
                
            # BUY orders fill when price <= limit_price
            # SELL orders fill when price >= limit_price
            should_fill = (
                (order.side == "BUY" and price <= order.limit_price) or
                (order.side == "SELL" and price >= order.limit_price)
            )
            
            if should_fill:
                filled_orders.append(order)
                orders_to_remove.append(order_id)
        
        # Remove filled orders from the book
        for order_id in orders_to_remove:
            del self._orders[order_id]
        
        return filled_orders

    def get_pending_orders(self, symbol: str | None = None) -> list[LimitOrder]:
        """Get all pending orders, optionally filtered by symbol.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of pending orders
        """
        if symbol is None:
            return list(self._orders.values())
        return [order for order in self._orders.values() if order.symbol == symbol]

    def get_order(self, order_id: int) -> LimitOrder | None:
        """Get a specific order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            LimitOrder if found, None otherwise
        """
        return self._orders.get(order_id)
