from __future__ import annotations

from typing import Protocol, Sequence

from core.types import PositionSnapshot, WalletSnapshot


class PortfolioProvider(Protocol):
    def fetch_wallets(self, *, exchange: str) -> Sequence[WalletSnapshot]:
        """Fetch wallet balances."""

    def fetch_positions(self, *, exchange: str) -> Sequence[PositionSnapshot]:
        """Fetch open positions (if the venue supports them)."""
