from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from core.persistence.interfaces import (
    AuditEventStore,
    CandleGapStore,
    CandleStore,
    ExchangeStore,
    ExecutionStore,
    FeeScheduleStore,
    MarketDataJobRunStore,
    MarketDataJobStore,
    OpportunityStore,
    OrderStore,
    PositionStore,
    StrategyStore,
    SymbolStore,
    TradeFillStore,
    WalletSnapshotStore,
)
from core.types import (
    Candle,
    CandleGap,
    Exchange,
    ExecutionResult,
    FeeSchedule,
    MarketDataJob,
    MarketDataJobRun,
    Opportunity,
    OrderIntent,
    OrderRecord,
    PositionSnapshot,
    Strategy,
    Symbol,
    TradeFill,
    WalletSnapshot,
)


class NoopCandleStore(CandleStore):
    def upsert_candles(self, *, candles: Sequence[Candle]) -> int:
        raise NotImplementedError("NoopCandleStore")

    def get_candles(
        self,
        *,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]:
        raise NotImplementedError("NoopCandleStore")


class NoopOpportunityStore(OpportunityStore):
    def log_opportunity(self, *, opportunity: Opportunity, exchange: str | None = None) -> None:
        raise NotImplementedError("NoopOpportunityStore")


class NoopExecutionStore(ExecutionStore):
    def log_intent(self, *, intent: OrderIntent) -> int:
        raise NotImplementedError("NoopExecutionStore")

    def log_result(self, *, intent_id: int | None, result: ExecutionResult) -> None:
        raise NotImplementedError("NoopExecutionStore")


class NoopAuditEventStore(AuditEventStore):
    def log_event(
        self,
        *,
        event_type: str,
        message: str,
        severity: str = "info",
        event_time: datetime | None = None,
        context_json: str | None = None,
    ) -> None:
        raise NotImplementedError("NoopAuditEventStore")


class NoopExchangeStore(ExchangeStore):
    def upsert_exchanges(self, *, exchanges: Sequence[Exchange]) -> int:
        raise NotImplementedError("NoopExchangeStore")

    def get_exchange(self, *, code: str) -> Optional[Exchange]:
        raise NotImplementedError("NoopExchangeStore")


class NoopSymbolStore(SymbolStore):
    def upsert_symbols(self, *, symbols: Sequence[Symbol]) -> int:
        raise NotImplementedError("NoopSymbolStore")

    def get_symbols(self, *, exchange_code: str | None = None, symbol: str | None = None) -> Sequence[Symbol]:
        raise NotImplementedError("NoopSymbolStore")


class NoopStrategyStore(StrategyStore):
    def upsert_strategies(self, *, strategies: Sequence[Strategy]) -> int:
        raise NotImplementedError("NoopStrategyStore")

    def get_strategy(self, *, name: str) -> Optional[Strategy]:
        raise NotImplementedError("NoopStrategyStore")


class NoopMarketDataJobStore(MarketDataJobStore):
    def create_job(self, *, job: MarketDataJob) -> int:
        raise NotImplementedError("NoopMarketDataJobStore")

    def update_job_status(self, *, job_id: int, status: str, last_error: str | None = None) -> None:
        raise NotImplementedError("NoopMarketDataJobStore")

    def get_jobs(
        self,
        *,
        exchange: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> Sequence[MarketDataJob]:
        raise NotImplementedError("NoopMarketDataJobStore")


class NoopMarketDataJobRunStore(MarketDataJobRunStore):
    def start_run(self, *, job_id: int) -> int:
        raise NotImplementedError("NoopMarketDataJobRunStore")

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
        raise NotImplementedError("NoopMarketDataJobRunStore")

    def get_runs(self, *, job_id: int, limit: int = 100) -> Sequence[MarketDataJobRun]:
        raise NotImplementedError("NoopMarketDataJobRunStore")


class NoopCandleGapStore(CandleGapStore):
    def log_gap(self, *, gap: CandleGap) -> int:
        raise NotImplementedError("NoopCandleGapStore")

    def mark_repaired(self, *, gap_id: int, repaired_at: datetime | None = None, notes: str | None = None) -> None:
        raise NotImplementedError("NoopCandleGapStore")

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
        raise NotImplementedError("NoopCandleGapStore")


class NoopWalletSnapshotStore(WalletSnapshotStore):
    def log_snapshot(self, *, snapshot: WalletSnapshot) -> int:
        raise NotImplementedError("NoopWalletSnapshotStore")

    def get_latest(self, *, exchange: str, currency: str) -> Optional[WalletSnapshot]:
        raise NotImplementedError("NoopWalletSnapshotStore")


class NoopPositionStore(PositionStore):
    def log_snapshot(self, *, snapshot: PositionSnapshot) -> int:
        raise NotImplementedError("NoopPositionStore")

    def get_latest(self, *, exchange: str, symbol: str) -> Optional[PositionSnapshot]:
        raise NotImplementedError("NoopPositionStore")


class NoopOrderStore(OrderStore):
    def upsert_order(self, *, order: OrderRecord) -> int:
        raise NotImplementedError("NoopOrderStore")

    def get_orders(
        self,
        *,
        exchange: str,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[OrderRecord]:
        raise NotImplementedError("NoopOrderStore")


class NoopTradeFillStore(TradeFillStore):
    def upsert_fill(self, *, fill: TradeFill) -> int:
        raise NotImplementedError("NoopTradeFillStore")

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
        raise NotImplementedError("NoopTradeFillStore")


class NoopFeeScheduleStore(FeeScheduleStore):
    def log_schedule(self, *, schedule: FeeSchedule) -> int:
        raise NotImplementedError("NoopFeeScheduleStore")

    def get_latest(self, *, exchange: str, symbol: str | None = None) -> Optional[FeeSchedule]:
        raise NotImplementedError("NoopFeeScheduleStore")
