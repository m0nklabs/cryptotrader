"""Dossier generation queue — staggers LLM work to reduce hardware stress.

Instead of hammering the GPU/CPU with back-to-back LLM calls, this module
spaces out dossier generation with configurable delays and provides
status tracking so the frontend can show progress.

Usage (standalone):
    from core.dossier.queue import DossierQueue
    q = DossierQueue(delay_seconds=10)
    asyncio.create_task(q.enqueue_all("bitfinex"))

Usage (from API — fire-and-forget):
    The /dossier/generate-all endpoint starts the queue in the background
    and returns immediately.  Status is available via /dossier/queue/status.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.dossier.service import DossierService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class QueueState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class QueueItem:
    """Tracks a single symbol's generation status."""

    symbol: str
    status: str = "pending"  # pending | running | done | failed
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    generation_ms: int = 0


@dataclass
class QueueStatus:
    """Snapshot of the current queue state."""

    state: QueueState = QueueState.IDLE
    exchange: str = ""
    total: int = 0
    completed: int = 0
    failed: int = 0
    current_symbol: str | None = None
    items: list[QueueItem] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    delay_seconds: float = 10.0

    def to_dict(self) -> dict:
        """Serialize for API response."""
        return {
            "state": self.state.value,
            "exchange": self.exchange,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "current_symbol": self.current_symbol,
            "progress_pct": round((self.completed + self.failed) / self.total * 100, 1) if self.total > 0 else 0,
            "items": [
                {
                    "symbol": i.symbol,
                    "status": i.status,
                    "error": i.error,
                    "generation_ms": i.generation_ms,
                }
                for i in self.items
            ],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "delay_seconds": self.delay_seconds,
        }


# ---------------------------------------------------------------------------
# Singleton queue
# ---------------------------------------------------------------------------

_queue_instance: DossierQueue | None = None


def get_queue(delay_seconds: float = 10.0) -> DossierQueue:
    """Get or create the singleton DossierQueue."""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = DossierQueue(delay_seconds=delay_seconds)
    return _queue_instance


class DossierQueue:
    """Staggered dossier generation queue.

    Generates dossiers one at a time with a configurable delay
    between each to spread GPU/CPU load.
    """

    def __init__(
        self,
        delay_seconds: float = 10.0,
        service: DossierService | None = None,
    ):
        self.delay_seconds = delay_seconds
        self._service = service or DossierService()
        self._status = QueueStatus(delay_seconds=delay_seconds)
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def status(self) -> QueueStatus:
        """Current queue status (read-only snapshot)."""
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status.state == QueueState.RUNNING

    async def enqueue_all(self, exchange: str = "bitfinex") -> QueueStatus:
        """Start generating dossiers for all symbols on an exchange.

        Returns immediately — work happens in a background task.
        If already running, returns current status without restarting.
        """
        async with self._lock:
            if self.is_running:
                logger.info("Queue already running, returning current status")
                return self._status

            # Get symbols
            symbols = await self._service._get_available_symbols(exchange)
            if not symbols:
                logger.warning(f"No symbols found for {exchange}")
                return self._status

            # Initialize queue items
            self._status = QueueStatus(
                state=QueueState.RUNNING,
                exchange=exchange,
                total=len(symbols),
                items=[QueueItem(symbol=s) for s in symbols],
                started_at=datetime.utcnow(),
                delay_seconds=self.delay_seconds,
            )

            logger.info(f"🚀 Dossier queue started: {len(symbols)} symbols, {self.delay_seconds}s delay between each")

            # Fire background task
            self._task = asyncio.create_task(self._process_queue(exchange))
            return self._status

    async def enqueue_symbol(self, exchange: str, symbol: str) -> QueueStatus:
        """Add a single symbol to generate (or generate immediately if idle)."""
        if self.is_running:
            # Check if symbol is already in the queue
            for item in self._status.items:
                if item.symbol == symbol:
                    return self._status
            # Add to end of queue
            self._status.items.append(QueueItem(symbol=symbol))
            self._status.total += 1
            return self._status

        # Not running — just do it directly
        self._status = QueueStatus(
            state=QueueState.RUNNING,
            exchange=exchange,
            total=1,
            items=[QueueItem(symbol=symbol)],
            started_at=datetime.utcnow(),
            delay_seconds=0,
        )
        self._task = asyncio.create_task(self._process_queue(exchange))
        return self._status

    async def _process_queue(self, exchange: str) -> None:
        """Process all queued symbols sequentially with delays."""
        try:
            for i, item in enumerate(self._status.items):
                if item.status != "pending":
                    continue

                # Update status
                item.status = "running"
                item.started_at = time.monotonic()
                self._status.current_symbol = item.symbol

                logger.info(f"📝 [{i + 1}/{self._status.total}] Generating dossier for {exchange}:{item.symbol}")

                try:
                    entry = await self._service.generate_entry(exchange, item.symbol)
                    item.status = "done"
                    item.finished_at = time.monotonic()
                    item.generation_ms = int((item.finished_at - item.started_at) * 1000)
                    self._status.completed += 1

                    logger.info(
                        f"  ✅ {item.symbol}: {entry.predicted_direction} → "
                        f"${entry.predicted_target:,.2f} "
                        f"({item.generation_ms}ms)"
                    )
                except Exception as e:
                    item.status = "failed"
                    item.error = str(e)
                    item.finished_at = time.monotonic()
                    item.generation_ms = int((item.finished_at - item.started_at) * 1000)
                    self._status.failed += 1
                    logger.error(f"  ❌ {item.symbol}: {e}")

                # Delay before next symbol (skip after last one)
                remaining = [it for it in self._status.items[i + 1 :] if it.status == "pending"]
                if remaining and self.delay_seconds > 0:
                    logger.debug(f"  ⏳ Waiting {self.delay_seconds}s before next symbol...")
                    await asyncio.sleep(self.delay_seconds)

            self._status.state = QueueState.COMPLETED
            self._status.current_symbol = None
            self._status.finished_at = datetime.utcnow()

            logger.info(
                f"🏁 Queue completed: {self._status.completed} done, "
                f"{self._status.failed} failed out of {self._status.total}"
            )

        except asyncio.CancelledError:
            logger.info("Queue cancelled")
            self._status.state = QueueState.FAILED
            self._status.current_symbol = None
            raise
        except Exception as e:
            logger.exception(f"Queue crashed: {e}")
            self._status.state = QueueState.FAILED
            self._status.current_symbol = None

    def cancel(self) -> bool:
        """Cancel the running queue."""
        if self._task and not self._task.done():
            self._task.cancel()
            self._status.state = QueueState.IDLE
            self._status.current_symbol = None
            logger.info("Queue cancelled by user")
            return True
        return False
