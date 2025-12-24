from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from core.execution.order_book import OrderBook
from core.types import ExecutionResult, OrderIntent


@dataclass
class PaperPosition:
    """Represents a paper trading position."""

    symbol: str
    qty: Decimal  # Positive for long, negative for short
    avg_entry: Decimal
    realized_pnl: Decimal = Decimal("0")


@dataclass
class PaperOrder:
    """Represents a paper trading order."""

    order_id: int
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["market", "limit"]
    qty: Decimal
    limit_price: Optional[Decimal] = None
    status: Literal["PENDING", "FILLED", "CANCELLED"] = "PENDING"
    fill_price: Optional[Decimal] = None
    slippage_bps: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None


class PaperExecutor:
    """Paper trading executor with order book simulation and position tracking.

    Features:
    - Market orders: instant fill at specified price ± slippage
    - Limit orders: fill when price crosses limit level
    - Position tracking: maintains long/short positions with average entry price
    - P&L calculation: tracks realized and unrealized P&L
    """

    def __init__(
        self,
        *,
        database_url: Optional[str] = None,
        default_slippage_bps: Decimal = Decimal("5"),
    ) -> None:
        """Initialize the paper executor.

        Args:
            database_url: Optional PostgreSQL connection URL for persistence
            default_slippage_bps: Default slippage in basis points for market orders
        """
        self._database_url = database_url
        self._default_slippage_bps = default_slippage_bps
        self._order_book = OrderBook()
        self._positions: dict[str, PaperPosition] = {}
        self._orders: dict[int, PaperOrder] = {}
        self._next_order_id = 1

    def execute(self, order: OrderIntent) -> ExecutionResult:
        """Legacy dry-run execute method for compatibility.

        This never places real orders. It returns what *would* have been executed.
        """
        return ExecutionResult(
            dry_run=True,
            accepted=True,
            reason="paper-execution",
            order_id=None,
            raw={
                "exchange": order.exchange,
                "symbol": order.symbol,
                "side": order.side,
                "amount": str(order.amount),
                "order_type": order.order_type,
                "limit_price": str(order.limit_price) if order.limit_price is not None else None,
            },
        )

    def execute_paper_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        qty: Decimal,
        order_type: Literal["market", "limit"] = "market",
        limit_price: Optional[Decimal] = None,
        market_price: Optional[Decimal] = None,
        slippage_bps: Optional[Decimal] = None,
    ) -> PaperOrder:
        """Execute a paper trading order.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            qty: Order quantity
            order_type: 'market' or 'limit'
            limit_price: Required for limit orders
            market_price: Current market price (required for market orders)
            slippage_bps: Slippage in basis points (optional, uses default if not specified)

        Returns:
            PaperOrder with execution details

        Raises:
            ValueError: If invalid parameters provided
        """
        if qty <= 0:
            raise ValueError("Quantity must be positive")

        if order_type == "limit" and limit_price is None:
            raise ValueError("Limit price required for limit orders")

        if order_type == "market" and market_price is None:
            raise ValueError("Market price required for market orders")

        order_id = self._next_order_id
        self._next_order_id += 1

        now = datetime.now(timezone.utc)
        slippage = slippage_bps if slippage_bps is not None else self._default_slippage_bps

        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            limit_price=limit_price,
            slippage_bps=slippage,
            created_at=now,
        )

        if order_type == "market":
            # Fill market order immediately with slippage
            assert market_price is not None
            fill_price = self._apply_slippage(market_price, side, slippage)
            order.fill_price = fill_price
            order.filled_at = now
            order.status = "FILLED"
            self._update_position(symbol, side, qty, fill_price)
        else:
            # Add limit order to order book with the same order_id
            assert limit_price is not None
            order.status = "PENDING"
            self._order_book.add_order(symbol, side, qty, limit_price, order_id=order_id)

        self._orders[order_id] = order

        # Persist to database if configured
        if self._database_url:
            self._persist_order(order)

        return order

    def update_market_price(self, symbol: str, price: Decimal) -> list[PaperOrder]:
        """Update market price and check for limit order fills.

        Args:
            symbol: Trading symbol
            price: Current market price

        Returns:
            List of orders that were filled
        """
        filled_orders = []
        limit_orders = self._order_book.check_fills(symbol, price)

        for limit_order in limit_orders:
            # Find the corresponding PaperOrder
            for order in self._orders.values():
                if (
                    order.order_id == limit_order.order_id
                    and order.status == "PENDING"
                ):
                    # Fill the order at limit price
                    order.fill_price = limit_order.limit_price
                    order.filled_at = datetime.now(timezone.utc)
                    order.status = "FILLED"
                    self._update_position(
                        order.symbol, order.side, order.qty, order.fill_price
                    )
                    filled_orders.append(order)

                    # Persist update if database configured
                    if self._database_url:
                        self._persist_order(order)
                    break

        return filled_orders

    def get_position(self, symbol: str) -> Optional[PaperPosition]:
        """Get current position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            PaperPosition if exists, None otherwise
        """
        return self._positions.get(symbol)

    def get_unrealized_pnl(self, symbol: str, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L for a position.

        Args:
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            Unrealized P&L (positive = profit, negative = loss)
        """
        position = self._positions.get(symbol)
        if position is None or position.qty == 0:
            return Decimal("0")

        # P&L = (current_price - avg_entry) * qty
        return (current_price - position.avg_entry) * position.qty

    def get_order(self, order_id: int) -> Optional[PaperOrder]:
        """Get order by ID.

        Args:
            order_id: Order ID

        Returns:
            PaperOrder if found, None otherwise
        """
        return self._orders.get(order_id)

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a pending limit order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled, False if not found or already filled
        """
        order = self._orders.get(order_id)
        if order is None or order.status != "PENDING":
            return False

        order.status = "CANCELLED"
        self._order_book.cancel_order(order_id)

        # Persist update if database configured
        if self._database_url:
            self._persist_order(order)

        return True

    def _apply_slippage(
        self, price: Decimal, side: Literal["BUY", "SELL"], slippage_bps: Decimal
    ) -> Decimal:
        """Apply slippage to a price.

        Args:
            price: Base price
            side: BUY or SELL
            slippage_bps: Slippage in basis points

        Returns:
            Price with slippage applied
        """
        slippage_factor = Decimal("1") + (slippage_bps / Decimal("10000"))
        if side == "BUY":
            # BUY orders pay more due to slippage
            return price * slippage_factor
        else:
            # SELL orders receive less due to slippage
            return price / slippage_factor

    def _update_position(
        self, symbol: str, side: Literal["BUY", "SELL"], qty: Decimal, price: Decimal
    ) -> None:
        """Update position after a trade.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            qty: Trade quantity
            price: Fill price
        """
        position = self._positions.get(symbol)

        # Convert side to signed quantity (positive for long, negative for short)
        signed_qty = qty if side == "BUY" else -qty

        if position is None:
            # New position
            self._positions[symbol] = PaperPosition(
                symbol=symbol,
                qty=signed_qty,
                avg_entry=price,
                realized_pnl=Decimal("0"),
            )
        else:
            # Existing position
            if (position.qty > 0 and signed_qty > 0) or (position.qty < 0 and signed_qty < 0):
                # Adding to position - update average entry
                total_cost = (position.avg_entry * abs(position.qty)) + (price * qty)
                new_qty = position.qty + signed_qty
                position.avg_entry = total_cost / abs(new_qty)
                position.qty = new_qty
            elif abs(signed_qty) < abs(position.qty):
                # Reducing position - realize P&L
                pnl_per_unit = (price - position.avg_entry) * (1 if position.qty > 0 else -1)
                realized_pnl = pnl_per_unit * qty
                position.realized_pnl += realized_pnl
                position.qty += signed_qty
            else:
                # Closing or flipping position
                closing_qty = abs(position.qty)
                pnl_per_unit = (price - position.avg_entry) * (1 if position.qty > 0 else -1)
                realized_pnl = pnl_per_unit * closing_qty
                position.realized_pnl += realized_pnl

                remaining_qty = abs(signed_qty) - closing_qty
                if remaining_qty > 0:
                    # Flipping to opposite side
                    position.qty = remaining_qty if signed_qty > 0 else -remaining_qty
                    position.avg_entry = price
                else:
                    # Fully closed
                    position.qty = Decimal("0")
                    position.avg_entry = Decimal("0")

        # Persist position if database configured
        if self._database_url:
            self._persist_position(position)

    def _persist_order(self, order: PaperOrder) -> None:
        """Persist order to database.

        Args:
            order: Order to persist
        """
        try:
            from sqlalchemy import create_engine, text  # type: ignore[import-not-found]
        except (ImportError, ModuleNotFoundError):
            return  # Silently skip if SQLAlchemy not available

        engine = create_engine(self._database_url, echo=False)

        stmt = text(
            """
            INSERT INTO paper_orders (
                id, symbol, side, order_type, qty, limit_price,
                status, fill_price, slippage_bps, created_at, filled_at
            )
            VALUES (
                :id, :symbol, :side, :order_type, :qty, :limit_price,
                :status, :fill_price, :slippage_bps, :created_at, :filled_at
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                fill_price = EXCLUDED.fill_price,
                filled_at = EXCLUDED.filled_at
            """
        )

        with engine.begin() as conn:
            conn.execute(
                stmt,
                {
                    "id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "order_type": order.order_type,
                    "qty": order.qty,
                    "limit_price": order.limit_price,
                    "status": order.status,
                    "fill_price": order.fill_price,
                    "slippage_bps": order.slippage_bps,
                    "created_at": order.created_at,
                    "filled_at": order.filled_at,
                },
            )

    def _persist_position(self, position: PaperPosition) -> None:
        """Persist position to database.

        Args:
            position: Position to persist
        """
        try:
            from sqlalchemy import create_engine, text  # type: ignore[import-not-found]
        except (ImportError, ModuleNotFoundError):
            return  # Silently skip if SQLAlchemy not available

        engine = create_engine(self._database_url, echo=False)

        stmt = text(
            """
            INSERT INTO paper_positions (symbol, qty, avg_entry, realized_pnl, updated_at)
            VALUES (:symbol, :qty, :avg_entry, :realized_pnl, :updated_at)
            ON CONFLICT (symbol) DO UPDATE SET
                qty = EXCLUDED.qty,
                avg_entry = EXCLUDED.avg_entry,
                realized_pnl = EXCLUDED.realized_pnl,
                updated_at = EXCLUDED.updated_at
            """
        )

        with engine.begin() as conn:
            conn.execute(
                stmt,
                {
                    "symbol": position.symbol,
                    "qty": position.qty,
                    "avg_entry": position.avg_entry,
                    "realized_pnl": position.realized_pnl,
                    "updated_at": datetime.now(timezone.utc),
                },
            )


# Convenience function for backwards compatibility
@dataclass(frozen=True)
class LegacyPaperExecutor:
    """Dry-run executor.

    This never places real orders. It returns what *would* have been executed.
    """

    def execute(self, order: OrderIntent) -> ExecutionResult:
        return ExecutionResult(
            dry_run=True,
            accepted=True,
            reason="paper-execution",
            order_id=None,
            raw={
                "exchange": order.exchange,
                "symbol": order.symbol,
                "side": order.side,
                "amount": str(order.amount),
                "order_type": order.order_type,
                "limit_price": str(order.limit_price) if order.limit_price is not None else None,
            },
        )
