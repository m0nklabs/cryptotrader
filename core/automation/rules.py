"""Rule and policy configuration for automation engine.

Defines configuration models for global and per-symbol automation rules,
including position sizing, trade limits, cooldowns, and slippage guards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class SymbolConfig:
    """Per-symbol automation configuration."""

    symbol: str
    enabled: bool = True
    max_position_size: Optional[Decimal] = None  # Max position size in base currency
    max_daily_trades: Optional[int] = None  # Max trades per day for this symbol
    cooldown_seconds: int = 0  # Min seconds between trades
    max_slippage_bps: Optional[int] = None  # Max allowed slippage in basis points
    timeout_seconds: int = 30  # Order timeout


@dataclass
class AutomationConfig:
    """Global automation configuration with safety parameters."""

    # Global kill switch
    enabled: bool = False  # Default: automation disabled

    # Per-symbol configurations
    symbol_configs: dict[str, SymbolConfig] = field(default_factory=dict)

    # Global position limits
    max_total_position_value: Optional[Decimal] = None  # Max total portfolio exposure
    max_position_size_default: Optional[Decimal] = None  # Default max position size

    # Global trade limits
    max_daily_trades_global: Optional[int] = None  # Max trades per day across all symbols
    cooldown_seconds_default: int = 60  # Default cooldown between trades

    # Global slippage and timeouts
    max_slippage_bps_default: Optional[int] = None  # Default max slippage (None = no limit)
    timeout_seconds_default: int = 30  # Default order timeout

    # Daily loss limits
    max_daily_loss: Optional[Decimal] = None  # Max loss per day (absolute value)
    max_daily_loss_percent: Optional[Decimal] = None  # Max loss as % of portfolio

    # Balance requirements
    min_balance_required: Optional[Decimal] = None  # Minimum balance to trade

    def get_symbol_config(self, symbol: str) -> SymbolConfig:
        """Get configuration for a specific symbol, or create default."""
        if symbol not in self.symbol_configs:
            return SymbolConfig(
                symbol=symbol,
                enabled=True,
                max_position_size=self.max_position_size_default,
                max_slippage_bps=self.max_slippage_bps_default,
                timeout_seconds=self.timeout_seconds_default,
                cooldown_seconds=self.cooldown_seconds_default,
            )
        return self.symbol_configs[symbol]

    def is_symbol_enabled(self, symbol: str) -> bool:
        """Check if trading is enabled for a symbol."""
        if not self.enabled:
            return False
        config = self.get_symbol_config(symbol)
        return config.enabled


@dataclass
class TradeHistory:
    """Track trade history for cooldown and limit enforcement."""

    trades: list[TradeRecord] = field(default_factory=list)

    def add_trade(self, symbol: str, timestamp: datetime) -> None:
        """Record a new trade."""
        self.trades.append(TradeRecord(symbol=symbol, timestamp=timestamp))

    def get_trades_since(self, since: datetime) -> list[TradeRecord]:
        """Get all trades since a specific time."""
        return [t for t in self.trades if t.timestamp >= since]

    def get_symbol_trades_since(self, symbol: str, since: datetime) -> list[TradeRecord]:
        """Get trades for a specific symbol since a specific time."""
        return [t for t in self.trades if t.symbol == symbol and t.timestamp >= since]

    def get_last_trade_time(self, symbol: str) -> Optional[datetime]:
        """Get timestamp of last trade for a symbol."""
        symbol_trades = [t for t in self.trades if t.symbol == symbol]
        if not symbol_trades:
            return None
        return max(t.timestamp for t in symbol_trades)

    def get_daily_trade_count(self, symbol: Optional[str] = None) -> int:
        """Get count of trades today (global or per-symbol)."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if symbol:
            return len(self.get_symbol_trades_since(symbol, today_start))
        return len(self.get_trades_since(today_start))


@dataclass(frozen=True)
class TradeRecord:
    """Simple trade record for tracking."""

    symbol: str
    timestamp: datetime
