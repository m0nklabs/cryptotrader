from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from core.execution.order_book import OrderBook
from core.fees.model import FeeModel
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
    status: Literal["PENDING", "FILLED", "CANCELLED", "PARTIAL", "MISSED"] = "PENDING"
    fill_price: Optional[Decimal] = None
    fill_qty: Optional[Decimal] = None  # For partial fills
    slippage_bps: Optional[Decimal] = None
    fees: Decimal = Decimal("0")  # Fees paid on this order
    fill_ratio: Optional[Decimal] = None  # For partial fills: fill_qty / qty
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None


class PaperExecutor:
    """Paper trading executor with order book simulation and position tracking.

    Features:
    - Market orders: instant fill at specified price +/- slippage
    - Limit orders: fill when price crosses limit level
    - Position tracking: maintains long/short positions with average entry price
    - Realistic fees: taker/maker fees, spread, and slippage deducted from P&L
    - Partial fills: configurable fill probability based on volume
    - Missed fills: low-liquidity orders may not fill
    - P&L calculation: tracks realized and unrealized P&L including fees
    """

    def __init__(
        self,
        *,
        database_url: Optional[str] = None,
        fee_model: Optional[FeeModel] = None,
        default_slippage_bps: Decimal = Decimal("5"),
        partial_fill_prob: Decimal = Decimal("0.9"),  # 90% chance of partial fill
        missed_fill_prob: Decimal = Decimal("0.02"),  # 2% chance of missed fill
        min_fill_ratio: Decimal = Decimal("0.5"),  # Minimum fill ratio for partial to count
    ) -> None:
        """Initialize the paper executor.

        Args:
            database_url: Optional PostgreSQL connection URL for persistence
            fee_model: Fee model for realistic cost estimation. Defaults to standard Bitfinex-like fees.
            default_slippage_bps: Default slippage in basis points for market orders
            partial_fill_prob: Probability of a partial fill (0-1)
            missed_fill_prob: Probability of a missed fill (0-1)
            min_fill_ratio: Minimum fill ratio for a partial fill to be considered valid
        """
        self._database_url = database_url
        self._fee_model = fee_model or FeeModel()
        self._default_slippage_bps = default_slippage_bps
        self._partial_fill_prob = partial_fill_prob
        self._missed_fill_prob = missed_fill_prob
        self._min_fill_ratio = min_fill_ratio
        self._order_book = OrderBook()
        self._positions: dict[str, PaperPosition] = {}
        self._orders: dict[int, PaperOrder] = {}
        self._last_prices: dict[str, Decimal] = {}
        self._next_order_id = 1
        self._total_fees: Decimal = Decimal("0")
        self._total_fees_by_symbol: dict[str, Decimal] = {}

    def get_fee_model(self) -> FeeModel:
        """Return the current fee model."""
        return self._fee_model

    def get_total_fees(self) -> Decimal:
        """Return total fees paid across all orders."""
        return self._total_fees

    def get_fees_by_symbol(self, symbol: str) -> Decimal:
        """Return total fees for a specific symbol."""
        return self._total_fees_by_symbol.get(symbol, Decimal("0"))

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
        fee_tier: Literal["maker", "taker"] = "taker",
        price_update_time: Optional[datetime] = None,
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
            fee_tier: 'maker' for limit orders, 'taker' for market orders
            price_update_time: Optional timestamp to use as the causal boundary.
                If provided, used for created_at and filled_at instead of
                datetime.now(), preventing lookahead bias when the order is
                evaluated against a price update at a specific time.

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

        now = price_update_time if price_update_time is not None else datetime.now(timezone.utc)
        slippage = slippage_bps if slippage_bps is not None else self._default_slippage_bps

        # Determine actual fill price and fill qty
        fill_price = None
        fill_qty = qty
        status = "PENDING"
        fees = Decimal("0")

        if order_type == "market":
            assert market_price is not None
            fill_price = self._apply_slippage(market_price, side, slippage)

            # Simulate partial or missed fill for market orders
            fill_result = self._simulate_fill(qty, fill_price)
            fill_qty = fill_result["fill_qty"]
            raw_status = fill_result["status"]

            # Derive the persisted status: a filled order that did not fill
            # the requested quantity is a PARTIAL fill, so reporters
            # (summary, audit, API) see PARTIAL with requested/filled/remaining.
            if raw_status == "FILLED" and fill_qty < qty:
                status = "PARTIAL"
            else:
                status = raw_status

            # Calculate fees based on fill notional
            fill_notional = fill_price * fill_qty
            if fill_notional > 0:
                cost_estimate = self._fee_model.estimate_cost(
                    gross_notional=fill_notional,
                    taker=(fee_tier == "taker"),
                )
                fees = cost_estimate.estimated_total_cost

            if status in ("FILLED", "PARTIAL"):
                self._update_position(symbol, side, fill_qty, fill_price)
        else:
            # Limit order
            assert limit_price is not None
            fill_price = None  # Not filled yet
            status = "PENDING"
            fill_qty = qty
            self._order_book.add_order(symbol, side, qty, limit_price, order_id=order_id, created_at=now)

            # Calculate fees for limit orders using limit_price as expected fill price
            fill_notional = limit_price * fill_qty
            if fill_notional > 0:
                cost_estimate = self._fee_model.estimate_cost(
                    gross_notional=fill_notional,
                    taker=(fee_tier == "taker"),
                )
                fees = cost_estimate.estimated_total_cost

        order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            limit_price=limit_price,
            fill_price=fill_price,
            fill_qty=fill_qty,
            slippage_bps=slippage,
            fees=fees,
            fill_ratio=fill_qty / qty if qty > 0 else Decimal("1"),
            status=status,
            created_at=now,
            filled_at=now if status in ("FILLED", "PARTIAL") else None,
        )

        self._orders[order_id] = order

        # Track fees
        if fees > 0:
            self._total_fees += fees
            self._total_fees_by_symbol[symbol] = self._total_fees_by_symbol.get(symbol, Decimal("0")) + fees

        # Persist to database if configured
        if self._database_url:
            self._persist_order(order)

        return order

    def _simulate_fill(self, qty: Decimal, fill_price: Decimal) -> dict:
        """Simulate whether an order fills fully, partially, or misses.

        Uses deterministic simulation based on order_id and fill_price
        to avoid randomness in tests.

        Returns dict with 'fill_qty' and 'status'.
        """
        import hashlib

        # Deterministic hash based on order_id and price for reproducibility
        hash_input = f"{self._next_order_id}:{fill_price}"
        hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        rand = Decimal(hash_val % 10000) / Decimal(10000)  # 0-1

        if rand < self._missed_fill_prob:
            return {"fill_qty": Decimal("0"), "status": "MISSED"}
        elif rand < self._missed_fill_prob + (1 - self._missed_fill_prob) * (1 - self._partial_fill_prob):
            # Partial fill: fill between min_fill_ratio and 1.0
            partial_ratio = self._min_fill_ratio + rand * (1 - self._min_fill_ratio)
            return {"fill_qty": (qty * partial_ratio).quantize(Decimal("0.00000001")), "status": "FILLED"}
        else:
            return {"fill_qty": qty, "status": "FILLED"}

    def update_market_price(
        self,
        symbol: str,
        price: Decimal,
        price_update_time: Optional[datetime] = None,
    ) -> list[PaperOrder]:
        """Update market price and check for limit order fills.

        Validates timestamp ordering to prevent lookahead bias: the price_update_time
        is used as the causal boundary for fill detection. Orders created after
        price_update_time are excluded from fill checks, ensuring that future data
        does not influence current order state determinations.

        Args:
            symbol: Trading symbol
            price: Current market price
            price_update_time: Optional timestamp of the price update. If None,
                uses current time. Fills are causally tied to this timestamp.

        Returns:
            List of orders that were filled
        """
        if price_update_time is None:
            price_update_time = datetime.now(timezone.utc)

        self._last_prices[symbol] = price
        filled_orders = []
        limit_orders = self._order_book.check_fills(symbol, price, price_update_time)

        for limit_order in limit_orders:
            # Find the corresponding PaperOrder
            for order in self._orders.values():
                if order.order_id == limit_order.order_id and order.status == "PENDING":
                    # Fill the order at limit price
                    # Use the price_update_time as the causal timestamp for the fill,
                    # not datetime.now(), to prevent lookahead bias
                    order.fill_price = limit_order.limit_price
                    order.filled_at = price_update_time
                    order.status = "FILLED"
                    self._update_position(order.symbol, order.side, order.qty, order.fill_price)
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

    def get_last_price(self, symbol: str) -> Optional[Decimal]:
        """Get the last known market price for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Last price if available, None otherwise
        """
        return self._last_prices.get(symbol)

    def get_unrealized_pnl(self, symbol: str, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L for a position (including fees).

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

    def get_all_orders(self) -> list[PaperOrder]:
        """Get all orders (including pending and cancelled)."""
        return list(self._orders.values())

    def get_orders_by_symbol(self, symbol: str) -> list[PaperOrder]:
        """Get all orders for a specific symbol."""
        return [o for o in self._orders.values() if o.symbol == symbol]

    def get_orders_by_status(self, status: str) -> list[PaperOrder]:
        """Get all orders with a specific status."""
        return [o for o in self._orders.values() if o.status == status]

    def get_paper_summary(self) -> dict:
        """Get a comprehensive paper trading summary for operator visibility.

        Returns:
            Dict with paper trading state summary.
        """
        positions = {}
        for sym, pos in self._positions.items():
            if pos.qty != 0:
                positions[sym] = {
                    "qty": float(pos.qty),
                    "avg_entry": float(pos.avg_entry),
                    "realized_pnl": float(pos.realized_pnl),
                    "fees_paid": float(self._total_fees_by_symbol.get(sym, Decimal("0"))),
                }

        total_unrealized = sum(
            (self._last_prices.get(sym, pos.avg_entry) - pos.avg_entry) * pos.qty
            for sym, pos in self._positions.items()
            if pos.qty != 0
        )

        return {
            "total_fees": float(self._total_fees),
            "total_unrealized_pnl": float(total_unrealized),
            "positions": positions,
            "orders": {
                "total": len(self._orders),
                "filled": len([o for o in self._orders.values() if o.status == "FILLED"]),
                "partial": len([o for o in self._orders.values() if o.status == "PARTIAL"]),
                "missed": len([o for o in self._orders.values() if o.status == "MISSED"]),
                "pending": len([o for o in self._orders.values() if o.status == "PENDING"]),
                "cancelled": len([o for o in self._orders.values() if o.status == "CANCELLED"]),
            },
            "fee_model": {
                "maker_fee": str(self._fee_model.breakdown.maker_fee_rate),
                "taker_fee": str(self._fee_model.breakdown.taker_fee_rate),
                "spread_bps": self._fee_model.breakdown.assumed_spread_bps,
                "slippage_bps": self._fee_model.breakdown.assumed_slippage_bps,
            },
        }

    def _apply_slippage(self, price: Decimal, side: Literal["BUY", "SELL"], slippage_bps: Decimal) -> Decimal:
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

    def _update_position(self, symbol: str, side: Literal["BUY", "SELL"], qty: Decimal, price: Decimal) -> None:
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
