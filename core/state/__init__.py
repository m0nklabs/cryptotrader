"""In-memory state manager for paper trading.

Provides a unified interface to hold and manage all in-memory data structures:
- Account balances (available/reserved per asset)
- Open positions (long/short with P&L)
- Orders (market/limit with fill tracking)
- Market prices (last known price per symbol)
"""

from core.state.manager import StateManager, StateSnapshot

__all__ = ["StateManager", "StateSnapshot"]
