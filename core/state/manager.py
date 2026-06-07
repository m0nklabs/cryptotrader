"""In-memory state manager for paper trading.

Provides a unified interface to hold and manage all in-memory data structures:
- Account balances (available/reserved per asset)
- Open positions (long/short with P&L)
- Orders (market/limit with fill tracking)
- Market prices (last known price per symbol)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.portfolio.balances import Balance, BalanceManager
from core.portfolio.positions import Position, PositionManager, PositionSide
from core.execution.paper import PaperExecutor, PaperOrder, PaperPosition
from core.execution.order_book import OrderBook


@dataclass
class StateSnapshot:
    """Point-in-time snapshot of the full trading state."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Balances
    balances: dict[str, dict] = field(default_factory=dict)

    # Positions
    positions: list[dict] = field(default_factory=list)

    # Orders
    orders: list[dict] = field(default_factory=list)

    # Prices
    prices: dict[str, str] = field(default_factory=dict)

    # Metrics
    total_equity: str = "0"
    unrealized_pnl: str = "0"
    realized_pnl: str = "0"


class StateManager:
    """Unified in-memory state manager for paper trading.

    Coordinates all in-memory data structures:
    - BalanceManager: tracks available/reserved per asset
    - PositionManager: tracks open positions with P&L
    - PaperExecutor: tracks orders and positions
    - OrderBook: tracks pending limit orders

    Thread-safety: Not thread-safe. Use external locking if needed.
    """

    def __init__(
        self,
        initial_balances: Optional[dict[str, Decimal]] = None,
        quote_currency: str = "USD",
    ) -> None:
        """Initialize state manager.

        Args:
            initial_balances: Starting balances per asset
            quote_currency: Quote currency for the portfolio
        """
        self._quote_currency = quote_currency
        self._balances = BalanceManager(initial_balances=initial_balances)
        self._positions = PositionManager()
        self._paper_executor = PaperExecutor()
        self._order_book = OrderBook()
        self._last_prices: dict[str, Decimal] = {}
        self._total_realized_pnl: Decimal = Decimal("0")

        # Take initial snapshot
        self._last_snapshot = StateSnapshot()

    # ========== Properties ==========

    @property
    def quote_currency(self) -> str:
        """Get the quote currency."""
        return self._quote_currency

    @property
    def balances(self) -> BalanceManager:
        """Get the balance manager."""
        return self._balances

    @property
    def positions(self) -> PositionManager:
        """Get the position manager."""
        return self._positions

    @property
    def paper_executor(self) -> PaperExecutor:
        """Get the paper executor."""
        return self._paper_executor

    @property
    def order_book(self) -> OrderBook:
        """Get the order book."""
        return self._order_book

    @property
    def last_prices(self) -> dict[str, Decimal]:
        """Get the last known prices."""
        return dict(self._last_prices)

    # ========== Balance Operations ==========

    def get_balance(self, asset: str) -> Balance:
        """Get balance for an asset.

        Args:
            asset: Asset symbol

        Returns:
            Balance object
        """
        return self._balances.get_balance(asset)

    def get_available(self, asset: str) -> Decimal:
        """Get available (not reserved) balance for an asset.

        Args:
            asset: Asset symbol

        Returns:
            Available balance
        """
        return self._balances.get_available(asset)

    def get_all_balances(self) -> list[Balance]:
        """Get all non-zero balances.

        Returns:
            List of Balance objects
        """
        return self._balances.get_all_balances()

    def deposit(self, asset: str, amount: Decimal) -> Balance:
        """Deposit funds into the state.

        Args:
            asset: Asset symbol
            amount: Amount to deposit

        Returns:
            Updated balance
        """
        return self._balances.credit(asset, amount)

    def withdraw(self, asset: str, amount: Decimal) -> Balance:
        """Withdraw funds from the state.

        Args:
            asset: Asset symbol
            amount: Amount to withdraw

        Returns:
            Updated balance

        Raises:
            ValueError: If insufficient available balance
        """
        return self._balances.debit(asset, amount)

    def reserve(self, asset: str, amount: Decimal) -> Balance:
        """Reserve funds for a pending order.

        Args:
            asset: Asset symbol
            amount: Amount to reserve

        Returns:
            Updated balance

        Raises:
            ValueError: If insufficient available balance
        """
        return self._balances.reserve(asset, amount)

    def release(self, asset: str, amount: Decimal) -> Balance:
        """Release reserved funds.

        Args:
            asset: Asset symbol
            amount: Amount to release

        Returns:
            Updated balance

        Raises:
            ValueError: If insufficient reserved balance
        """
        return self._balances.release(asset, amount)

    def settle_reserved(self, asset: str, amount: Decimal) -> Balance:
        """Settle reserved funds (order filled).

        Args:
            asset: Asset symbol
            amount: Amount to settle

        Returns:
            Updated balance

        Raises:
            ValueError: If insufficient reserved balance
        """
        return self._balances.settle_reserved(asset, amount)

    # ========== Position Operations ==========

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            Position if exists, None otherwise
        """
        return self._positions.get_position(symbol)

    def get_all_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of Position objects
        """
        return self._positions.get_all_positions()

    def has_position(self, symbol: str) -> bool:
        """Check if a position exists for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            True if position exists
        """
        return self._positions.has_position(symbol)

    def open_long(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> Position:
        """Open or increase a long position.

        Args:
            symbol: Trading pair
            quantity: Amount to buy
            price: Entry price

        Returns:
            Updated position

        Raises:
            ValueError: If quantity <= 0 or price <= 0
        """
        return self._positions.open_position(
            symbol=symbol,
            side=PositionSide.LONG,
            quantity=quantity,
            price=price,
        )

    def open_short(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> Position:
        """Open or increase a short position.

        Args:
            symbol: Trading pair
            quantity: Amount to sell short
            price: Entry price

        Returns:
            Updated position

        Raises:
            ValueError: If quantity <= 0 or price <= 0
        """
        return self._positions.open_position(
            symbol=symbol,
            side=PositionSide.SHORT,
            quantity=quantity,
            price=price,
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
            Closed position with realized P&L

        Raises:
            ValueError: If no position exists
        """
        existing = self._positions.get_position(symbol)
        if existing is None:
            raise ValueError(f"No position exists for {symbol}")

        close_qty = quantity if quantity is not None else existing.quantity

        # Calculate P&L before closing
        if existing.side == PositionSide.LONG:
            pnl = (price - existing.avg_entry_price) * close_qty
            # Return principal + P&L
            proceeds = (existing.avg_entry_price * close_qty) + pnl
            self._balances.credit(self._quote_currency, proceeds)
        else:  # SHORT
            pnl = (existing.avg_entry_price - price) * close_qty
            # Credit/debit based on P&L
            if pnl > 0:
                self._balances.credit(self._quote_currency, pnl)
            elif pnl < 0:
                self._balances.debit(self._quote_currency, abs(pnl))

        # Track realized P&L
        self._total_realized_pnl += pnl

        position = self._positions.close_position(symbol, price, quantity)
        return position

    # ========== Order Operations ==========

    def execute_market_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        market_price: Decimal,
        slippage_bps: Optional[Decimal] = None,
    ) -> PaperOrder:
        """Execute a market order through the paper executor.

        Args:
            symbol: Trading pair
            side: BUY or SELL
            qty: Order quantity
            market_price: Current market price
            slippage_bps: Slippage in basis points

        Returns:
            PaperOrder with execution details
        """
        return self._paper_executor.execute_paper_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="market",
            market_price=market_price,
            slippage_bps=slippage_bps,
        )

    def execute_limit_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        limit_price: Decimal,
    ) -> PaperOrder:
        """Execute a limit order through the paper executor.

        Args:
            symbol: Trading pair
            side: BUY or SELL
            qty: Order quantity
            limit_price: Limit price

        Returns:
            PaperOrder with execution details
        """
        return self._paper_executor.execute_paper_order(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="limit",
            limit_price=limit_price,
        )

    def get_order(self, order_id: int) -> Optional[PaperOrder]:
        """Get order by ID.

        Args:
            order_id: Order ID

        Returns:
            PaperOrder if found
        """
        return self._paper_executor.get_order(order_id)

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a pending order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled, False otherwise
        """
        return self._paper_executor.cancel_order(order_id)

    def get_all_orders(self) -> list[PaperOrder]:
        """Get all orders.

        Returns:
            List of all orders
        """
        return self._paper_executor.get_all_orders()

    def get_orders_by_status(self, status: str) -> list[PaperOrder]:
        """Get orders filtered by status.

        Args:
            status: Order status (PENDING, FILLED, etc.)

        Returns:
            List of matching orders
        """
        return self._paper_executor.get_orders_by_status(status)

    # ========== Price Operations ==========

    def update_price(self, symbol: str, price: Decimal) -> None:
        """Update the last known price for a symbol.

        Args:
            symbol: Trading pair
            price: New price
        """
        self._last_prices[symbol] = price
        self._paper_executor.update_market_price(symbol, price)

    def get_price(self, symbol: str) -> Optional[Decimal]:
        """Get the last known price for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            Last price or None if not set
        """
        return self._last_prices.get(symbol)

    def get_unrealized_pnl(self, symbol: str, current_price: Decimal) -> Decimal:
        """Get unrealized P&L for a symbol's position.

        Uses the PositionManager (not PaperExecutor) positions since
        open_long/open_short update PositionManager.

        Args:
            symbol: Trading pair
            current_price: Current market price

        Returns:
            Unrealized P&L
        """
        position = self._positions.get_position(symbol)
        if position is None:
            return Decimal("0")
        return position.unrealized_pnl(current_price)

    # ========== Portfolio Metrics ==========

    def get_total_equity(self) -> Decimal:
        """Calculate total portfolio equity.

        Returns:
            Total equity (available + reserved + position values)
        """
        quote_balance = self._balances.get_balance(self._quote_currency)
        total = quote_balance.total

        # Add position values
        for position in self._positions.get_all_positions():
            price = self._last_prices.get(position.symbol)
            if price is not None:
                if position.side == PositionSide.LONG:
                    total += position.quantity * price
                else:
                    total += position.quantity * price  # Negative for shorts
            else:
                total += position.notional

        return total

    def get_total_unrealized_pnl(self) -> Decimal:
        """Calculate total unrealized P&L across all positions.

        Returns:
            Total unrealized P&L
        """
        total = Decimal("0")
        for position in self._positions.get_all_positions():
            price = self._last_prices.get(position.symbol)
            if price is not None:
                total += position.unrealized_pnl(price)
        return total

    def get_total_realized_pnl(self) -> Decimal:
        """Get total realized P&L from all closed trades.

        Returns:
            Total realized P&L
        """
        return self._total_realized_pnl

    def get_total_fees(self) -> Decimal:
        """Get total fees paid across all orders.

        Returns:
            Total fees
        """
        return self._paper_executor.get_total_fees()

    # ========== State Queries ==========

    def get_paper_position(self, symbol: str) -> Optional[PaperPosition]:
        """Get the paper executor's position for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            PaperPosition if exists
        """
        return self._paper_executor.get_position(symbol)

    def get_last_price(self, symbol: str) -> Optional[Decimal]:
        """Get the last known market price.

        Args:
            symbol: Trading pair

        Returns:
            Last price or None
        """
        return self._paper_executor.get_last_price(symbol)

    def get_paper_summary(self) -> dict:
        """Get a comprehensive state summary.

        Returns:
            Dict with full state summary
        """
        return self._paper_executor.get_paper_summary()

    # ========== Snapshot ==========

    def take_snapshot(self) -> StateSnapshot:
        """Capture the current state as a snapshot.

        Returns:
            StateSnapshot with current state
        """
        snapshot = StateSnapshot(
            timestamp=datetime.now(timezone.utc),
            balances={
                b.asset: {
                    "available": str(b.available),
                    "reserved": str(b.reserved),
                    "total": str(b.total),
                }
                for b in self._balances.get_all_balances()
            },
            positions=[
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "quantity": str(p.quantity),
                    "avg_entry_price": str(p.avg_entry_price),
                    "realized_pnl": str(p.realized_pnl),
                }
                for p in self._positions.get_all_positions()
            ],
            orders=[
                {
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "order_type": o.order_type,
                    "qty": str(o.qty),
                    "status": o.status,
                    "fill_price": str(o.fill_price) if o.fill_price else None,
                    "fill_qty": str(o.fill_qty) if o.fill_qty else None,
                }
                for o in self._paper_executor.get_all_orders()
            ],
            prices={
                k: str(v) for k, v in self._last_prices.items()
            },
            total_equity=str(self.get_total_equity()),
            unrealized_pnl=str(self.get_total_unrealized_pnl()),
            realized_pnl=str(self.get_total_realized_pnl()),
        )

        self._last_snapshot = snapshot
        return snapshot

    def get_last_snapshot(self) -> Optional[StateSnapshot]:
        """Get the most recent snapshot.

        Returns:
            Last snapshot or None
        """
        return self._last_snapshot

    # ========== Reset ==========

    def reset(self, initial_balances: Optional[dict[str, Decimal]] = None) -> None:
        """Reset the state to initial values.

        Args:
            initial_balances: New initial balances (replaces current)
        """
        self._balances = BalanceManager(initial_balances=initial_balances)
        self._positions = PositionManager()
        self._paper_executor = PaperExecutor()
        self._order_book = OrderBook()
        self._last_prices = {}
        self._total_realized_pnl = Decimal("0")
        self._last_snapshot = StateSnapshot()
