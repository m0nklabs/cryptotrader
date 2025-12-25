"""Portfolio position management.

Tracks open positions with P&L calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4


class PositionSide(str, Enum):
    """Position direction."""

    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Position:
    """Represents an open position."""

    id: str
    symbol: str
    side: PositionSide
    quantity: Decimal
    avg_entry_price: Decimal
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    realized_pnl: Decimal = Decimal("0")
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def notional(self) -> Decimal:
        """Position notional value at entry."""
        return self.quantity * self.avg_entry_price

    def unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        """Calculate unrealized P&L at current mark price.

        Args:
            mark_price: Current market price

        Returns:
            Unrealized P&L (positive = profit)
        """
        if self.side == PositionSide.LONG:
            return (mark_price - self.avg_entry_price) * self.quantity
        else:  # SHORT
            return (self.avg_entry_price - mark_price) * self.quantity

    def pnl_percent(self, mark_price: Decimal) -> Decimal:
        """Calculate unrealized P&L as percentage of entry.

        Args:
            mark_price: Current market price

        Returns:
            P&L percentage (e.g., 0.05 = 5%)
        """
        if self.notional == 0:
            return Decimal("0")
        return self.unrealized_pnl(mark_price) / self.notional


class PositionManager:
    """Manages open positions.

    Supports:
    - Open/increase positions
    - Reduce/close positions with P&L
    - Position queries
    """

    def __init__(self) -> None:
        """Initialize position manager."""
        self._positions: dict[str, Position] = {}  # symbol -> Position

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol.

        Args:
            symbol: Trading pair (e.g., 'BTC/USD')

        Returns:
            Position if exists, None otherwise
        """
        return self._positions.get(symbol)

    def get_all_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of Position objects
        """
        return list(self._positions.values())

    def has_position(self, symbol: str) -> bool:
        """Check if position exists for symbol.

        Args:
            symbol: Trading pair

        Returns:
            True if position exists
        """
        return symbol in self._positions

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: Decimal,
        price: Decimal,
    ) -> Position:
        """Open a new position or increase existing.

        If position exists in same direction, averages in.
        If position exists in opposite direction, reduces/flips.

        Args:
            symbol: Trading pair
            side: LONG or SHORT
            quantity: Amount to open (must be > 0)
            price: Entry price

        Returns:
            Updated or new Position

        Raises:
            ValueError: If quantity <= 0 or price <= 0
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")

        existing = self._positions.get(symbol)

        if existing is None:
            # New position
            position = Position(
                id=str(uuid4()),
                symbol=symbol,
                side=side,
                quantity=quantity,
                avg_entry_price=price,
            )
            self._positions[symbol] = position
            return position

        if existing.side == side:
            # Same direction: average in
            total_qty = existing.quantity + quantity
            new_avg = ((existing.avg_entry_price * existing.quantity) + (price * quantity)) / total_qty

            position = Position(
                id=existing.id,
                symbol=symbol,
                side=side,
                quantity=total_qty,
                avg_entry_price=new_avg,
                opened_at=existing.opened_at,
                realized_pnl=existing.realized_pnl,
            )
            self._positions[symbol] = position
            return position

        # Opposite direction: reduce or flip
        if quantity < existing.quantity:
            # Partial close
            pnl = self._calculate_close_pnl(existing, quantity, price)
            position = Position(
                id=existing.id,
                symbol=symbol,
                side=existing.side,
                quantity=existing.quantity - quantity,
                avg_entry_price=existing.avg_entry_price,
                opened_at=existing.opened_at,
                realized_pnl=existing.realized_pnl + pnl,
            )
            self._positions[symbol] = position
            return position

        elif quantity > existing.quantity:
            # Close and flip
            close_pnl = self._calculate_close_pnl(existing, existing.quantity, price)
            remaining_qty = quantity - existing.quantity

            position = Position(
                id=str(uuid4()),
                symbol=symbol,
                side=side,
                quantity=remaining_qty,
                avg_entry_price=price,
                realized_pnl=close_pnl,
            )
            self._positions[symbol] = position
            return position

        else:
            # Exact close
            pnl = self._calculate_close_pnl(existing, quantity, price)
            del self._positions[symbol]
            # Return closed position with final P&L
            return Position(
                id=existing.id,
                symbol=symbol,
                side=existing.side,
                quantity=Decimal("0"),
                avg_entry_price=existing.avg_entry_price,
                opened_at=existing.opened_at,
                realized_pnl=existing.realized_pnl + pnl,
            )

    def close_position(
        self,
        symbol: str,
        price: Decimal,
        quantity: Optional[Decimal] = None,
    ) -> Position:
        """Close a position partially or fully.

        Args:
            symbol: Trading pair
            price: Exit price
            quantity: Amount to close (None = close all)

        Returns:
            Closed/reduced Position with realized P&L

        Raises:
            ValueError: If no position exists or quantity > position size
        """
        position = self._positions.get(symbol)
        if position is None:
            raise ValueError(f"No position exists for {symbol}")

        close_qty = quantity if quantity is not None else position.quantity

        if close_qty > position.quantity:
            raise ValueError(f"Cannot close {close_qty} when position is only {position.quantity}")

        pnl = self._calculate_close_pnl(position, close_qty, price)

        if close_qty == position.quantity:
            # Full close
            del self._positions[symbol]
            return Position(
                id=position.id,
                symbol=symbol,
                side=position.side,
                quantity=Decimal("0"),
                avg_entry_price=position.avg_entry_price,
                opened_at=position.opened_at,
                realized_pnl=position.realized_pnl + pnl,
            )

        # Partial close
        updated = Position(
            id=position.id,
            symbol=symbol,
            side=position.side,
            quantity=position.quantity - close_qty,
            avg_entry_price=position.avg_entry_price,
            opened_at=position.opened_at,
            realized_pnl=position.realized_pnl + pnl,
        )
        self._positions[symbol] = updated
        return updated

    def _calculate_close_pnl(
        self,
        position: Position,
        quantity: Decimal,
        exit_price: Decimal,
    ) -> Decimal:
        """Calculate realized P&L for closing a position.

        Args:
            position: Position being closed
            quantity: Amount being closed
            exit_price: Exit price

        Returns:
            Realized P&L for this close
        """
        if position.side == PositionSide.LONG:
            return (exit_price - position.avg_entry_price) * quantity
        else:  # SHORT
            return (position.avg_entry_price - exit_price) * quantity
