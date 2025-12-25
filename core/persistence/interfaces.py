from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, Sequence

from core.types import (
    Candle,
    CandleGap,
    ExecutionResult,
    Exchange,
    FeeSchedule,
    MarketDataJob,
    MarketDataJobRun,
    Opportunity,
    OrderIntent,
    OrderRecord,
    PaperOrder,
    PaperPosition,
    PortfolioSnapshot,
    PositionSnapshot,
    Strategy,
    Symbol,
    TradeFill,
    WalletSnapshot,
)


class CandleStore(Protocol):
    def upsert_candles(self, *, candles: Sequence[Candle]) -> int:
        """Insert or update candles. Returns number of affected rows."""

    def get_candles(
        self,
        *,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]:
        """Fetch candles for a time range."""


class OpportunityStore(Protocol):
    def log_opportunity(self, *, opportunity: Opportunity, exchange: str | None = None) -> None:
        """Persist a scored opportunity snapshot."""


class ExecutionStore(Protocol):
    def log_intent(self, *, intent: OrderIntent) -> int:
        """Persist an execution intent and return its id."""

    def log_result(self, *, intent_id: int | None, result: ExecutionResult) -> None:
        """Persist an execution result tied to an optional intent id."""


class AuditEventStore(Protocol):
    def log_event(
        self,
        *,
        event_type: str,
        message: str,
        severity: str = "info",
        event_time: datetime | None = None,
        context_json: str | None = None,
    ) -> None:
        """Persist an audit event (decisions, safety checks, errors, etc.)."""


class ExchangeStore(Protocol):
    def upsert_exchanges(self, *, exchanges: Sequence[Exchange]) -> int:
        """Insert or update exchanges. Returns number of affected rows."""

    def get_exchange(self, *, code: str) -> Optional[Exchange]:
        """Fetch a single exchange by code."""


class SymbolStore(Protocol):
    def upsert_symbols(self, *, symbols: Sequence[Symbol]) -> int:
        """Insert or update symbols. Returns number of affected rows."""

    def get_symbols(self, *, exchange_code: str | None = None, symbol: str | None = None) -> Sequence[Symbol]:
        """Fetch symbols (optionally filtered by exchange_code and/or symbol)."""


class StrategyStore(Protocol):
    def upsert_strategies(self, *, strategies: Sequence[Strategy]) -> int:
        """Insert or update strategies. Returns number of affected rows."""

    def get_strategy(self, *, name: str) -> Optional[Strategy]:
        """Fetch a single strategy by name."""


class MarketDataJobStore(Protocol):
    def create_job(self, *, job: MarketDataJob) -> int:
        """Persist a market data job and return its id."""

    def update_job_status(self, *, job_id: int, status: str, last_error: str | None = None) -> None:
        """Update job status and optional last_error."""

    def get_jobs(
        self,
        *,
        exchange: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> Sequence[MarketDataJob]:
        """List jobs with optional filters."""


class MarketDataJobRunStore(Protocol):
    def start_run(self, *, job_id: int) -> int:
        """Create a run row and return its id."""

    def finish_run(
        self,
        *,
        run_id: int,
        status: str,
        candles_fetched: int = 0,
        candles_upserted: int = 0,
        last_open_time: datetime | None = None,
        last_error: str | None = None,
    ) -> None:
        """Mark a job run as finished (success/failed) with stats."""

    def get_runs(self, *, job_id: int, limit: int = 100) -> Sequence[MarketDataJobRun]:
        """List runs for a job."""


class CandleGapStore(Protocol):
    def log_gap(self, *, gap: CandleGap) -> int:
        """Persist a detected candle gap and return its id."""

    def mark_repaired(self, *, gap_id: int, repaired_at: datetime | None = None, notes: str | None = None) -> None:
        """Mark a gap as repaired."""

    def get_gaps(
        self,
        *,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        only_unrepaired: bool = False,
        limit: int = 1000,
    ) -> Sequence[CandleGap]:
        """Fetch gaps for a time range."""


class WalletSnapshotStore(Protocol):
    def log_snapshot(self, *, snapshot: WalletSnapshot) -> int:
        """Persist a wallet snapshot and return its id."""

    def get_latest(self, *, exchange: str, currency: str) -> Optional[WalletSnapshot]:
        """Fetch latest wallet snapshot for exchange+currency."""


class PositionStore(Protocol):
    def log_snapshot(self, *, snapshot: PositionSnapshot) -> int:
        """Persist a position snapshot and return its id."""

    def get_latest(self, *, exchange: str, symbol: str) -> Optional[PositionSnapshot]:
        """Fetch latest position snapshot for exchange+symbol."""


class OrderStore(Protocol):
    def upsert_order(self, *, order: OrderRecord) -> int:
        """Insert or update an order record and return affected row count or id."""

    def get_orders(
        self,
        *,
        exchange: str,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[OrderRecord]:
        """List orders with optional filters."""


class TradeFillStore(Protocol):
    def upsert_fill(self, *, fill: TradeFill) -> int:
        """Insert or update a trade fill and return affected row count or id."""

    def get_fills(
        self,
        *,
        exchange: str,
        symbol: str | None = None,
        order_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 5000,
    ) -> Sequence[TradeFill]:
        """List fills with optional filters."""


class FeeScheduleStore(Protocol):
    def log_schedule(self, *, schedule: FeeSchedule) -> int:
        """Persist a fee schedule snapshot and return its id."""

    def get_latest(self, *, exchange: str, symbol: str | None = None) -> Optional[FeeSchedule]:
        """Fetch latest fee schedule for exchange and optional symbol."""


class PaperOrderStore(Protocol):
    def create_order(self, *, order: PaperOrder) -> int:
        """Create a paper order and return its id."""

    def update_order_status(
        self,
        *,
        order_id: int,
        status: str,
        fill_price: Optional[float] = None,
        slippage_bps: Optional[float] = None,
        filled_at: datetime | None = None,
    ) -> None:
        """Update paper order status and fill details."""

    def get_orders(
        self,
        *,
        symbol: str | None = None,
        status: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[PaperOrder]:
        """List paper orders with optional filters."""


class PaperPositionStore(Protocol):
    def upsert_position(self, *, position: PaperPosition) -> int:
        """Insert or update a paper position and return affected row count or id."""

    def get_position(self, *, symbol: str) -> Optional[PaperPosition]:
        """Fetch current paper position for a symbol."""

    def get_all_positions(self) -> Sequence[PaperPosition]:
        """Fetch all current paper positions."""


class PortfolioSnapshotStore(Protocol):
    def log_snapshot(self, *, snapshot: PortfolioSnapshot) -> int:
        """Persist a portfolio snapshot and return its id."""

    def get_latest(self, *, exchange: str | None = None) -> Optional[PortfolioSnapshot]:
        """Fetch latest portfolio snapshot, optionally filtered by exchange."""

    def get_snapshots(
        self,
        *,
        exchange: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[PortfolioSnapshot]:
        """List portfolio snapshots with optional filters."""
