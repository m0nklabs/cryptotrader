"""Portfolio snapshots for equity tracking.

Captures portfolio state at points in time for performance analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional


@dataclass
class PortfolioSnapshot:
    """Point-in-time snapshot of portfolio state."""

    timestamp: datetime
    total_equity: Decimal
    available_balance: Decimal
    reserved_balance: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    position_count: int

    @property
    def total_pnl(self) -> Decimal:
        """Total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl


class EquityCurve:
    """Tracks portfolio equity over time.

    Supports:
    - Recording snapshots
    - Calculating drawdown
    - Performance metrics
    """

    def __init__(self, max_snapshots: int = 10000) -> None:
        """Initialize equity curve.

        Args:
            max_snapshots: Maximum snapshots to retain (oldest dropped)
        """
        self._snapshots: list[PortfolioSnapshot] = []
        self._max_snapshots = max_snapshots
        self._peak_equity: Decimal = Decimal("0")

    def record(self, snapshot: PortfolioSnapshot) -> None:
        """Record a snapshot.

        Args:
            snapshot: Portfolio snapshot to record
        """
        self._snapshots.append(snapshot)

        # Track peak for drawdown
        if snapshot.total_equity > self._peak_equity:
            self._peak_equity = snapshot.total_equity

        # Trim if over limit
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots :]

    def get_snapshots(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[PortfolioSnapshot]:
        """Get snapshots in time range.

        Args:
            start: Start time (inclusive)
            end: End time (inclusive)

        Returns:
            List of snapshots in range
        """
        result = self._snapshots
        if start:
            result = [s for s in result if s.timestamp >= start]
        if end:
            result = [s for s in result if s.timestamp <= end]
        return result

    @property
    def latest(self) -> Optional[PortfolioSnapshot]:
        """Get most recent snapshot."""
        return self._snapshots[-1] if self._snapshots else None

    @property
    def first(self) -> Optional[PortfolioSnapshot]:
        """Get first snapshot."""
        return self._snapshots[0] if self._snapshots else None

    @property
    def peak_equity(self) -> Decimal:
        """Get peak equity value."""
        return self._peak_equity

    @property
    def current_drawdown(self) -> Decimal:
        """Get current drawdown from peak (as positive decimal).

        Returns:
            Drawdown (e.g., 0.10 = 10% below peak)
        """
        if not self._snapshots or self._peak_equity == 0:
            return Decimal("0")

        current = self._snapshots[-1].total_equity
        if current >= self._peak_equity:
            return Decimal("0")

        return (self._peak_equity - current) / self._peak_equity

    @property
    def max_drawdown(self) -> Decimal:
        """Calculate maximum drawdown in history.

        Returns:
            Max drawdown (e.g., 0.25 = 25% max drop from peak)
        """
        if len(self._snapshots) < 2:
            return Decimal("0")

        peak = Decimal("0")
        max_dd = Decimal("0")

        for snapshot in self._snapshots:
            if snapshot.total_equity > peak:
                peak = snapshot.total_equity
            elif peak > 0:
                dd = (peak - snapshot.total_equity) / peak
                if dd > max_dd:
                    max_dd = dd

        return max_dd

    def total_return(self) -> Decimal:
        """Calculate total return from first to last snapshot.

        Returns:
            Total return (e.g., 0.50 = 50% gain)
        """
        if len(self._snapshots) < 2:
            return Decimal("0")

        first_equity = self._snapshots[0].total_equity
        if first_equity == 0:
            return Decimal("0")

        last_equity = self._snapshots[-1].total_equity
        return (last_equity - first_equity) / first_equity

    def __len__(self) -> int:
        """Number of snapshots."""
        return len(self._snapshots)


@dataclass
class SnapshotterConfig:
    """Configuration for automatic snapshot recording."""

    interval_seconds: int = 3600  # 1 hour default
    on_trade: bool = True  # Snapshot on each trade


class Snapshotter:
    """Automatic snapshot recorder.

    Captures portfolio state at intervals and on trades.
    """

    def __init__(
        self,
        equity_curve: EquityCurve,
        snapshot_fn: Callable[[], PortfolioSnapshot],
        config: Optional[SnapshotterConfig] = None,
    ) -> None:
        """Initialize snapshotter.

        Args:
            equity_curve: Equity curve to record to
            snapshot_fn: Function that returns current portfolio snapshot
            config: Snapshotter configuration
        """
        self._equity_curve = equity_curve
        self._snapshot_fn = snapshot_fn
        self._config = config or SnapshotterConfig()
        self._last_snapshot: Optional[datetime] = None

    def maybe_snapshot(self, force: bool = False) -> Optional[PortfolioSnapshot]:
        """Take a snapshot if interval has passed or forced.

        Args:
            force: Force snapshot regardless of interval

        Returns:
            Snapshot if taken, None otherwise
        """
        now = datetime.now(timezone.utc)

        if not force and self._last_snapshot:
            elapsed = (now - self._last_snapshot).total_seconds()
            if elapsed < self._config.interval_seconds:
                return None

        snapshot = self._snapshot_fn()
        self._equity_curve.record(snapshot)
        self._last_snapshot = now
        return snapshot

    def on_trade(self) -> Optional[PortfolioSnapshot]:
        """Record snapshot on trade if configured.

        Returns:
            Snapshot if taken, None otherwise
        """
        if self._config.on_trade:
            return self.maybe_snapshot(force=True)
        return None
