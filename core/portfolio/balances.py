"""Portfolio balance management.

Tracks available and reserved balances per asset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional


@dataclass
class Balance:
    """Represents a balance for a single asset."""

    asset: str
    available: Decimal
    reserved: Decimal = Decimal("0")
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total(self) -> Decimal:
        """Total balance (available + reserved)."""
        return self.available + self.reserved


class BalanceManager:
    """Manages balances for multiple assets.

    Supports:
    - Credit/debit operations
    - Reserve/release for pending orders
    - Balance queries
    """

    def __init__(self, initial_balances: Optional[dict[str, Decimal]] = None) -> None:
        """Initialize balance manager.

        Args:
            initial_balances: Optional dict of asset -> initial available balance
        """
        self._balances: dict[str, Balance] = {}
        if initial_balances:
            for asset, amount in initial_balances.items():
                self._balances[asset] = Balance(asset=asset, available=amount)

    def get_balance(self, asset: str) -> Balance:
        """Get balance for an asset.

        Args:
            asset: Asset symbol (e.g., 'USD', 'BTC')

        Returns:
            Balance object (creates with zero if not exists)
        """
        if asset not in self._balances:
            self._balances[asset] = Balance(asset=asset, available=Decimal("0"))
        return self._balances[asset]

    def get_available(self, asset: str) -> Decimal:
        """Get available balance for an asset.

        Args:
            asset: Asset symbol

        Returns:
            Available balance
        """
        return self.get_balance(asset).available

    def get_all_balances(self) -> list[Balance]:
        """Get all non-zero balances.

        Returns:
            List of Balance objects with total > 0
        """
        return [b for b in self._balances.values() if b.total > 0]

    def credit(self, asset: str, amount: Decimal) -> Balance:
        """Add funds to available balance.

        Args:
            asset: Asset symbol
            amount: Amount to add (must be > 0)

        Returns:
            Updated balance

        Raises:
            ValueError: If amount <= 0
        """
        if amount <= 0:
            raise ValueError("Credit amount must be positive")

        balance = self.get_balance(asset)
        self._balances[asset] = Balance(
            asset=asset,
            available=balance.available + amount,
            reserved=balance.reserved,
        )
        return self._balances[asset]

    def debit(self, asset: str, amount: Decimal) -> Balance:
        """Remove funds from available balance.

        Args:
            asset: Asset symbol
            amount: Amount to remove (must be > 0)

        Returns:
            Updated balance

        Raises:
            ValueError: If amount <= 0 or insufficient available balance
        """
        if amount <= 0:
            raise ValueError("Debit amount must be positive")

        balance = self.get_balance(asset)
        if balance.available < amount:
            raise ValueError(f"Insufficient available balance for {asset}: have {balance.available}, need {amount}")

        self._balances[asset] = Balance(
            asset=asset,
            available=balance.available - amount,
            reserved=balance.reserved,
        )
        return self._balances[asset]

    def reserve(self, asset: str, amount: Decimal) -> Balance:
        """Move funds from available to reserved (for pending orders).

        Args:
            asset: Asset symbol
            amount: Amount to reserve (must be > 0)

        Returns:
            Updated balance

        Raises:
            ValueError: If amount <= 0 or insufficient available balance
        """
        if amount <= 0:
            raise ValueError("Reserve amount must be positive")

        balance = self.get_balance(asset)
        if balance.available < amount:
            raise ValueError(
                f"Insufficient available balance to reserve for {asset}: have {balance.available}, need {amount}"
            )

        self._balances[asset] = Balance(
            asset=asset,
            available=balance.available - amount,
            reserved=balance.reserved + amount,
        )
        return self._balances[asset]

    def release(self, asset: str, amount: Decimal) -> Balance:
        """Move funds from reserved back to available (order cancelled).

        Args:
            asset: Asset symbol
            amount: Amount to release (must be > 0)

        Returns:
            Updated balance

        Raises:
            ValueError: If amount <= 0 or insufficient reserved balance
        """
        if amount <= 0:
            raise ValueError("Release amount must be positive")

        balance = self.get_balance(asset)
        if balance.reserved < amount:
            raise ValueError(
                f"Insufficient reserved balance to release for {asset}: have {balance.reserved}, need {amount}"
            )

        self._balances[asset] = Balance(
            asset=asset,
            available=balance.available + amount,
            reserved=balance.reserved - amount,
        )
        return self._balances[asset]

    def settle_reserved(self, asset: str, amount: Decimal) -> Balance:
        """Remove funds from reserved (order filled).

        Args:
            asset: Asset symbol
            amount: Amount to settle (must be > 0)

        Returns:
            Updated balance

        Raises:
            ValueError: If amount <= 0 or insufficient reserved balance
        """
        if amount <= 0:
            raise ValueError("Settle amount must be positive")

        balance = self.get_balance(asset)
        if balance.reserved < amount:
            raise ValueError(
                f"Insufficient reserved balance to settle for {asset}: have {balance.reserved}, need {amount}"
            )

        self._balances[asset] = Balance(
            asset=asset,
            available=balance.available,
            reserved=balance.reserved - amount,
        )
        return self._balances[asset]
