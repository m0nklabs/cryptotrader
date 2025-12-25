"""Portfolio manager - central coordinator.

Integrates balance, position, and snapshot management.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from .balances import Balance, BalanceManager
from .positions import Position, PositionManager, PositionSide
from .snapshots import EquityCurve, PortfolioSnapshot, Snapshotter, SnapshotterConfig


@dataclass
class PortfolioConfig:
    """Portfolio manager configuration."""

    quote_currency: str = "USD"
    initial_balance: Decimal = Decimal("10000")
    snapshot_interval_seconds: int = 3600
    snapshot_on_trade: bool = True


class PortfolioManager:
    """Central portfolio management.

    Coordinates:
    - Balance tracking (available/reserved)
    - Position management (open/close with P&L)
    - Equity curve snapshots

    Thread-safety: Not thread-safe. Use external locking if needed.
    """

    def __init__(
        self,
        config: Optional[PortfolioConfig] = None,
        price_provider: Optional[Callable[[str], Decimal]] = None,
    ) -> None:
        """Initialize portfolio manager.

        Args:
            config: Portfolio configuration
            price_provider: Function to get current price for a symbol
        """
        self._config = config or PortfolioConfig()
        self._price_provider = price_provider

        # Initialize balance manager with starting capital
        self._balances = BalanceManager(initial_balances={self._config.quote_currency: self._config.initial_balance})
        self._positions = PositionManager()
        self._equity_curve = EquityCurve()

        # Set up snapshotter
        snapshotter_config = SnapshotterConfig(
            interval_seconds=self._config.snapshot_interval_seconds,
            on_trade=self._config.snapshot_on_trade,
        )
        self._snapshotter = Snapshotter(
            equity_curve=self._equity_curve,
            snapshot_fn=self._create_snapshot,
            config=snapshotter_config,
        )

        # Take initial snapshot
        self._snapshotter.maybe_snapshot(force=True)

    # ========== Balance Operations ==========

    @property
    def quote_currency(self) -> str:
        """Get quote currency."""
        return self._config.quote_currency

    def get_balance(self, asset: str) -> Balance:
        """Get balance for an asset.

        Args:
            asset: Asset symbol

        Returns:
            Balance object
        """
        return self._balances.get_balance(asset)

    def get_available(self, asset: str) -> Decimal:
        """Get available balance for an asset.

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
        """Deposit funds.

        Args:
            asset: Asset symbol
            amount: Amount to deposit

        Returns:
            Updated balance
        """
        return self._balances.credit(asset, amount)

    def withdraw(self, asset: str, amount: Decimal) -> Balance:
        """Withdraw funds.

        Args:
            asset: Asset symbol
            amount: Amount to withdraw

        Returns:
            Updated balance

        Raises:
            ValueError: If insufficient available balance
        """
        return self._balances.debit(asset, amount)

    # ========== Position Operations ==========

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            Position if exists
        """
        return self._positions.get_position(symbol)

    def get_all_positions(self) -> list[Position]:
        """Get all open positions.

        Returns:
            List of positions
        """
        return self._positions.get_all_positions()

    def open_long(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> Position:
        """Open or increase a long position.

        Reserves quote currency and opens position.

        Args:
            symbol: Trading pair
            quantity: Amount to buy
            price: Entry price

        Returns:
            Updated position

        Raises:
            ValueError: If insufficient balance
        """
        cost = quantity * price
        self._balances.reserve(self._config.quote_currency, cost)

        try:
            position = self._positions.open_position(
                symbol=symbol,
                side=PositionSide.LONG,
                quantity=quantity,
                price=price,
            )
            # Settle the reserved funds
            self._balances.settle_reserved(self._config.quote_currency, cost)
            self._snapshotter.on_trade()
            return position
        except Exception:
            # Release reserved funds on error
            self._balances.release(self._config.quote_currency, cost)
            raise

    def open_short(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> Position:
        """Open or increase a short position.

        For paper trading, we don't require margin - just track the position.

        Args:
            symbol: Trading pair
            quantity: Amount to sell short
            price: Entry price

        Returns:
            Updated position
        """
        position = self._positions.open_position(
            symbol=symbol,
            side=PositionSide.SHORT,
            quantity=quantity,
            price=price,
        )
        self._snapshotter.on_trade()
        return position

    def close_position(
        self,
        symbol: str,
        price: Decimal,
        quantity: Optional[Decimal] = None,
    ) -> Position:
        """Close a position partially or fully.

        Credits P&L to quote currency balance.

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
            self._balances.credit(self._config.quote_currency, proceeds)
        else:  # SHORT
            pnl = (existing.avg_entry_price - price) * close_qty
            # Credit/debit based on P&L
            if pnl > 0:
                self._balances.credit(self._config.quote_currency, pnl)
            elif pnl < 0:
                self._balances.debit(self._config.quote_currency, abs(pnl))

        position = self._positions.close_position(symbol, price, quantity)
        self._snapshotter.on_trade()
        return position

    # ========== Portfolio Metrics ==========

    def get_total_equity(self) -> Decimal:
        """Calculate total portfolio equity.

        Returns:
            Total equity (cash balance + position mark values)
        """
        # Available + reserved quote balance
        quote_balance = self._balances.get_balance(self._config.quote_currency)
        total = quote_balance.total

        # Add position values at current mark price
        for position in self._positions.get_all_positions():
            if self._price_provider:
                mark_price = self._price_provider(position.symbol)
                if position.side == PositionSide.LONG:
                    # Long: position value = quantity * mark_price
                    total += position.quantity * mark_price
                else:
                    # Short: notional at entry + unrealized P&L
                    total += position.notional + position.unrealized_pnl(mark_price)
            else:
                # No price provider: use entry value
                total += position.notional

        return total

    def get_unrealized_pnl(self) -> Decimal:
        """Calculate total unrealized P&L across all positions.

        Returns:
            Total unrealized P&L
        """
        if not self._price_provider:
            return Decimal("0")

        total = Decimal("0")
        for position in self._positions.get_all_positions():
            mark_price = self._price_provider(position.symbol)
            total += position.unrealized_pnl(mark_price)
        return total

    def get_realized_pnl(self) -> Decimal:
        """Get total realized P&L from all closed trades.

        Returns:
            Total realized P&L
        """
        total = Decimal("0")
        for position in self._positions.get_all_positions():
            total += position.realized_pnl
        return total

    # ========== Snapshot Operations ==========

    @property
    def equity_curve(self) -> EquityCurve:
        """Get equity curve."""
        return self._equity_curve

    def take_snapshot(self) -> PortfolioSnapshot:
        """Force a portfolio snapshot.

        Returns:
            New snapshot
        """
        snapshot = self._snapshotter.maybe_snapshot(force=True)
        assert snapshot is not None
        return snapshot

    def _create_snapshot(self) -> PortfolioSnapshot:
        """Create a portfolio snapshot.

        Returns:
            Current portfolio snapshot
        """
        quote_balance = self._balances.get_balance(self._config.quote_currency)

        return PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            total_equity=self.get_total_equity(),
            available_balance=quote_balance.available,
            reserved_balance=quote_balance.reserved,
            unrealized_pnl=self.get_unrealized_pnl(),
            realized_pnl=self.get_realized_pnl(),
            position_count=len(self._positions.get_all_positions()),
        )

    # ========== Summary ==========

    def get_summary(self) -> dict:
        """Get portfolio summary.

        Returns:
            Dict with portfolio state
        """
        return {
            "quote_currency": self._config.quote_currency,
            "total_equity": float(self.get_total_equity()),
            "available_balance": float(self.get_available(self._config.quote_currency)),
            "unrealized_pnl": float(self.get_unrealized_pnl()),
            "realized_pnl": float(self.get_realized_pnl()),
            "position_count": len(self.get_all_positions()),
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side.value,
                    "quantity": float(p.quantity),
                    "avg_entry_price": float(p.avg_entry_price),
                    "unrealized_pnl": float(
                        p.unrealized_pnl(self._price_provider(p.symbol)) if self._price_provider else 0
                    ),
                }
                for p in self.get_all_positions()
            ],
            "max_drawdown": float(self._equity_curve.max_drawdown),
            "current_drawdown": float(self._equity_curve.current_drawdown),
        }
