from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional, Sequence

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
from core.storage.postgres.config import PostgresConfig
from core.types import (
    Candle,
    CandleGap,
    Exchange,
    ExecutionResult,
    FeeSchedule,
    IndicatorSignal,
    MarketDataJob,
    MarketDataJobRun,
    Opportunity,
    OpportunitySnapshot,
    OrderIntent,
    OrderRecord,
    PositionSnapshot,
    Strategy,
    Symbol,
    TradeFill,
    WalletSnapshot,
)


class PostgresStores(
    CandleStore,
    OpportunityStore,
    ExecutionStore,
    AuditEventStore,
    ExchangeStore,
    SymbolStore,
    StrategyStore,
    MarketDataJobStore,
    MarketDataJobRunStore,
    CandleGapStore,
    WalletSnapshotStore,
    PositionStore,
    OrderStore,
    TradeFillStore,
    FeeScheduleStore,
):
    """Single entrypoint for a PostgreSQL-backed persistence layer.

    This is a skeleton: method bodies are placeholders.
    Delegated work can implement these methods using SQLAlchemy or psycopg2.
    """

    def __init__(self, *, config: PostgresConfig) -> None:
        self._config = config
        self._engine: Any | None = None

    def _require_sqlalchemy(self) -> tuple[Any, Any]:
        try:
            from sqlalchemy import create_engine, text  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "SQLAlchemy is required for PostgresStores. Install optional deps from requirements.txt."
            ) from exc

        return create_engine, text

    def _get_engine(self) -> Any:
        if self._engine is None:
            create_engine, _ = self._require_sqlalchemy()
            # Do not log the URL (it may contain secrets).
            self._engine = create_engine(self._config.database_url, echo=False, pool_pre_ping=True)
        return self._engine

    def _get_latest_candle_open_time(self, *, exchange: str, symbol: str, timeframe: str) -> datetime | None:
        """Internal helper used by ingestion jobs (not part of the persistence Protocols)."""

        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            SELECT open_time
            FROM candles
            WHERE exchange = :exchange
              AND symbol = :symbol
              AND timeframe = :timeframe
            ORDER BY open_time DESC
            LIMIT 1
            """
        )

        with engine.begin() as conn:
            row = conn.execute(
                stmt,
                {"exchange": exchange, "symbol": symbol, "timeframe": timeframe},
            ).fetchone()

        return None if row is None else row[0]

    def get_latest_candle_closes(
        self,
        *,
        exchanges: Sequence[str],
        timeframe: str,
        symbols: Sequence[str] | None = None,
    ) -> Sequence[tuple[str, str, Any]]:
        if not exchanges:
            return []

        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        params: dict[str, Any] = {
            "exchanges": list(exchanges),
            "timeframe": timeframe,
            "symbols": list(symbols) if symbols else [],
        }

        stmt = text(
            """
            SELECT exchange, symbol, close
            FROM (
                SELECT
                    exchange,
                    symbol,
                    close,
                    ROW_NUMBER() OVER (
                        PARTITION BY exchange, symbol
                        ORDER BY open_time DESC
                    ) AS rn
                FROM candles
                WHERE exchange = ANY(:exchanges)
                  AND timeframe = :timeframe
                  AND (
                      cardinality(:symbols::text[]) = 0
                      OR symbol = ANY(:symbols::text[])
                  )
            ) t
            WHERE rn = 1
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(stmt, params).fetchall()

        return rows

    # ---- CandleStore

    def upsert_candles(self, *, candles: Sequence[Candle]) -> int:
        if not candles:
            return 0

        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        payload = [
            {
                "exchange": candle.exchange,
                "symbol": candle.symbol,
                "timeframe": str(candle.timeframe),
                "open_time": candle.open_time,
                "close_time": candle.close_time,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in candles
        ]

        stmt = text(
            """
            INSERT INTO candles (
                exchange, symbol, timeframe,
                open_time, close_time,
                open, high, low, close,
                volume
            )
            VALUES (
                :exchange, :symbol, :timeframe,
                :open_time, :close_time,
                :open, :high, :low, :close,
                :volume
            )
            ON CONFLICT (exchange, symbol, timeframe, open_time)
            DO UPDATE SET
                close_time = EXCLUDED.close_time,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            """
        )

        with engine.begin() as conn:
            result = conn.execute(stmt, payload)

        # Some drivers return unreliable rowcount for executemany; fall back to input size.
        return int(getattr(result, "rowcount", 0) or len(payload))

    def get_candles(
        self,
        *,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            SELECT
                exchange, symbol, timeframe,
                open_time, close_time,
                open, high, low, close,
                volume
            FROM candles
            WHERE exchange = :exchange
              AND symbol = :symbol
              AND timeframe = :timeframe
              AND open_time >= :start
              AND open_time <= :end
            ORDER BY open_time ASC
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(
                stmt,
                {
                    "exchange": exchange,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start": start,
                    "end": end,
                },
            ).fetchall()

        return [
            Candle(
                exchange=row[0],
                symbol=row[1],
                timeframe=row[2],
                open_time=row[3],
                close_time=row[4],
                open=row[5],
                high=row[6],
                low=row[7],
                close=row[8],
                volume=row[9],
            )
            for row in rows
        ]

    # ---- OpportunityStore

    def log_opportunity(self, *, opportunity: Opportunity, exchange: str | None = None) -> None:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        # Convert signals to JSON
        signals_list = [
            {
                "code": sig.code,
                "side": sig.side,
                "strength": sig.strength,
                "value": sig.value,
                "reason": sig.reason,
            }
            for sig in opportunity.signals
        ]
        signals_json = json.dumps(signals_list, separators=(",", ":"))

        stmt = text(
            """
            INSERT INTO opportunities (exchange, symbol, timeframe, score, side, signals_json)
            VALUES (:exchange, :symbol, :timeframe, :score, :side, :signals_json)
            """
        )

        with engine.begin() as conn:
            conn.execute(
                stmt,
                {
                    "exchange": exchange or "bitfinex",
                    "symbol": opportunity.symbol,
                    "timeframe": opportunity.timeframe,
                    "score": opportunity.score,
                    "side": opportunity.side,
                    "signals_json": signals_json,
                },
            )

    def get_opportunities(
        self,
        *,
        exchange: str = "bitfinex",
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 20,
    ) -> Sequence[OpportunitySnapshot]:
        """Fetch latest opportunities with optional filters."""
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        filters = ["exchange = :exchange"]
        params: dict[str, Any] = {"exchange": exchange, "limit": limit}

        if symbol:
            filters.append("symbol = :symbol")
            params["symbol"] = symbol

        if timeframe:
            filters.append("timeframe = :timeframe")
            params["timeframe"] = timeframe

        where_clause = " AND ".join(filters)

        stmt = text(
            f"""
            SELECT id, exchange, symbol, timeframe, score, side, signals_json, created_at
            FROM opportunities
            WHERE {where_clause}
            ORDER BY created_at DESC, score DESC
            LIMIT :limit
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(stmt, params).fetchall()

        results: list[OpportunitySnapshot] = []
        for row in rows:
            signals_json = row[6]
            signals: list[IndicatorSignal] = []

            if signals_json:
                try:
                    signals_data = json.loads(signals_json)
                    signals = [
                        IndicatorSignal(
                            code=sig["code"],
                            side=sig["side"],
                            strength=sig["strength"],
                            value=sig["value"],
                            reason=sig["reason"],
                        )
                        for sig in signals_data
                    ]
                except Exception:
                    signals = []

            results.append(
                OpportunitySnapshot(
                    exchange=row[1],
                    symbol=row[2],
                    timeframe=row[3],
                    score=row[4],
                    side=row[5],
                    signals=signals,
                    created_at=row[7],
                )
            )

        return results

    # ---- ExecutionStore

    def log_intent(self, *, intent: OrderIntent) -> int:
        raise NotImplementedError("PostgresStores.log_intent")

    def log_result(self, *, intent_id: int | None, result: ExecutionResult) -> None:
        raise NotImplementedError("PostgresStores.log_result")

    # ---- AuditEventStore

    def log_event(
        self,
        *,
        event_type: str,
        message: str,
        severity: str = "info",
        event_time: datetime | None = None,
        context_json: str | None = None,
    ) -> None:
        raise NotImplementedError("PostgresStores.log_event")

    # ---- ExchangeStore

    def upsert_exchanges(self, *, exchanges: Sequence[Exchange]) -> int:
        raise NotImplementedError("PostgresStores.upsert_exchanges")

    def get_exchange(self, *, code: str) -> Optional[Exchange]:
        raise NotImplementedError("PostgresStores.get_exchange")

    # ---- SymbolStore

    def upsert_symbols(self, *, symbols: Sequence[Symbol]) -> int:
        raise NotImplementedError("PostgresStores.upsert_symbols")

    def get_symbols(self, *, exchange_code: str | None = None, symbol: str | None = None) -> Sequence[Symbol]:
        raise NotImplementedError("PostgresStores.get_symbols")

    # ---- StrategyStore

    def upsert_strategies(self, *, strategies: Sequence[Strategy]) -> int:
        raise NotImplementedError("PostgresStores.upsert_strategies")

    def get_strategy(self, *, name: str) -> Optional[Strategy]:
        raise NotImplementedError("PostgresStores.get_strategy")

    # ---- MarketDataJobStore

    def create_job(self, *, job: MarketDataJob) -> int:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            INSERT INTO market_data_jobs (
                job_type, exchange, symbol, timeframe,
                start_time, end_time,
                status, last_error
            )
            VALUES (
                :job_type, :exchange, :symbol, :timeframe,
                :start_time, :end_time,
                :status, :last_error
            )
            RETURNING id
            """
        )

        with engine.begin() as conn:
            row = conn.execute(
                stmt,
                {
                    "job_type": job.job_type,
                    "exchange": job.exchange,
                    "symbol": job.symbol,
                    "timeframe": str(job.timeframe),
                    "start_time": job.start_time,
                    "end_time": job.end_time,
                    "status": job.status,
                    "last_error": job.last_error,
                },
            ).fetchone()

        if row is None:
            raise RuntimeError("Failed to create market_data_job")

        return int(row[0])

    def update_job_status(self, *, job_id: int, status: str, last_error: str | None = None) -> None:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            UPDATE market_data_jobs
            SET status = :status,
                last_error = :last_error
            WHERE id = :job_id
            """
        )

        with engine.begin() as conn:
            conn.execute(stmt, {"job_id": job_id, "status": status, "last_error": last_error})

    def get_jobs(
        self,
        *,
        exchange: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> Sequence[MarketDataJob]:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        conditions: list[str] = []
        params: dict[str, object] = {"limit": limit}

        if exchange is not None:
            conditions.append("exchange = :exchange")
            params["exchange"] = exchange
        if symbol is not None:
            conditions.append("symbol = :symbol")
            params["symbol"] = symbol
        if timeframe is not None:
            conditions.append("timeframe = :timeframe")
            params["timeframe"] = timeframe
        if status is not None:
            conditions.append("status = :status")
            params["status"] = status

        where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        stmt = text(
            f"""
            SELECT
                job_type, exchange, symbol, timeframe,
                start_time, end_time,
                status, last_error
            FROM market_data_jobs
            {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(stmt, params).fetchall()

        return [
            MarketDataJob(
                job_type=row[0],
                exchange=row[1],
                symbol=row[2],
                timeframe=row[3],
                start_time=row[4],
                end_time=row[5],
                status=row[6],
                last_error=row[7],
            )
            for row in rows
        ]

    # ---- MarketDataJobRunStore

    def start_run(self, *, job_id: int) -> int:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            INSERT INTO market_data_job_runs (job_id)
            VALUES (:job_id)
            RETURNING id
            """
        )

        with engine.begin() as conn:
            row = conn.execute(stmt, {"job_id": job_id}).fetchone()

        if row is None:
            raise RuntimeError("Failed to start market_data_job_run")

        return int(row[0])

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
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            UPDATE market_data_job_runs
            SET finished_at = CURRENT_TIMESTAMP,
                status = :status,
                candles_fetched = :candles_fetched,
                candles_upserted = :candles_upserted,
                last_open_time = :last_open_time,
                last_error = :last_error
            WHERE id = :run_id
            """
        )

        with engine.begin() as conn:
            conn.execute(
                stmt,
                {
                    "run_id": run_id,
                    "status": status,
                    "candles_fetched": candles_fetched,
                    "candles_upserted": candles_upserted,
                    "last_open_time": last_open_time,
                    "last_error": last_error,
                },
            )

    def get_runs(self, *, job_id: int, limit: int = 100) -> Sequence[MarketDataJobRun]:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            SELECT
                job_id,
                started_at,
                finished_at,
                status,
                candles_fetched,
                candles_upserted,
                last_open_time,
                last_error
            FROM market_data_job_runs
            WHERE job_id = :job_id
            ORDER BY started_at DESC
            LIMIT :limit
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(stmt, {"job_id": job_id, "limit": limit}).fetchall()

        return [
            MarketDataJobRun(
                job_id=row[0],
                started_at=row[1],
                finished_at=row[2],
                status=row[3],
                candles_fetched=int(row[4] or 0),
                candles_upserted=int(row[5] or 0),
                last_open_time=row[6],
                last_error=row[7],
            )
            for row in rows
        ]

    # ---- CandleGapStore

    def log_gap(self, *, gap: CandleGap) -> int:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            INSERT INTO candle_gaps (
                exchange, symbol, timeframe,
                expected_open_time, expected_close_time,
                detected_at, repaired_at,
                notes
            )
            VALUES (
                :exchange, :symbol, :timeframe,
                :expected_open_time, :expected_close_time,
                COALESCE(:detected_at, CURRENT_TIMESTAMP), :repaired_at,
                :notes
            )
            ON CONFLICT (exchange, symbol, timeframe, expected_open_time)
            DO UPDATE SET
                expected_close_time = COALESCE(EXCLUDED.expected_close_time, candle_gaps.expected_close_time),
                notes = COALESCE(EXCLUDED.notes, candle_gaps.notes)
            RETURNING id
            """
        )

        with engine.begin() as conn:
            row = conn.execute(
                stmt,
                {
                    "exchange": gap.exchange,
                    "symbol": gap.symbol,
                    "timeframe": str(gap.timeframe),
                    "expected_open_time": gap.expected_open_time,
                    "expected_close_time": gap.expected_close_time,
                    "detected_at": gap.detected_at,
                    "repaired_at": gap.repaired_at,
                    "notes": gap.notes,
                },
            ).fetchone()

        if row is None:
            raise RuntimeError("Failed to log candle gap")
        return int(row[0])

    def mark_repaired(self, *, gap_id: int, repaired_at: datetime | None = None, notes: str | None = None) -> None:
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        stmt = text(
            """
            UPDATE candle_gaps
            SET repaired_at = COALESCE(:repaired_at, CURRENT_TIMESTAMP),
                notes = COALESCE(:notes, notes)
            WHERE id = :gap_id
            """
        )

        with engine.begin() as conn:
            conn.execute(stmt, {"gap_id": gap_id, "repaired_at": repaired_at, "notes": notes})

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
        engine = self._get_engine()
        _, text = self._require_sqlalchemy()

        conditions: list[str] = [
            "exchange = :exchange",
            "symbol = :symbol",
            "timeframe = :timeframe",
        ]
        params: dict[str, object] = {
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
        }

        if start is not None:
            conditions.append("expected_open_time >= :start")
            params["start"] = start
        if end is not None:
            conditions.append("expected_open_time <= :end")
            params["end"] = end
        if only_unrepaired:
            conditions.append("repaired_at IS NULL")

        where_sql = " AND ".join(conditions)

        stmt = text(
            f"""
            SELECT
                exchange, symbol, timeframe,
                expected_open_time, expected_close_time,
                detected_at, repaired_at,
                notes
            FROM candle_gaps
            WHERE {where_sql}
            ORDER BY expected_open_time ASC
            LIMIT :limit
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(stmt, params).fetchall()

        return [
            CandleGap(
                exchange=row[0],
                symbol=row[1],
                timeframe=row[2],
                expected_open_time=row[3],
                expected_close_time=row[4],
                detected_at=row[5],
                repaired_at=row[6],
                notes=row[7],
            )
            for row in rows
        ]

    # ---- WalletSnapshotStore

    def log_snapshot(self, *, snapshot: WalletSnapshot) -> int:
        raise NotImplementedError("PostgresStores.log_wallet_snapshot")

    def get_latest(self, *, exchange: str, currency: str) -> Optional[WalletSnapshot]:
        raise NotImplementedError("PostgresStores.get_latest_wallet_snapshot")

    # ---- PositionStore

    def log_snapshot(self, *, snapshot: PositionSnapshot) -> int:
        raise NotImplementedError("PostgresStores.log_position_snapshot")

    def get_latest(self, *, exchange: str, symbol: str) -> Optional[PositionSnapshot]:
        raise NotImplementedError("PostgresStores.get_latest_position")

    # ---- OrderStore

    def upsert_order(self, *, order: OrderRecord) -> int:
        raise NotImplementedError("PostgresStores.upsert_order")

    def get_orders(
        self,
        *,
        exchange: str,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> Sequence[OrderRecord]:
        raise NotImplementedError("PostgresStores.get_orders")

    # ---- TradeFillStore

    def upsert_fill(self, *, fill: TradeFill) -> int:
        raise NotImplementedError("PostgresStores.upsert_fill")

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
        raise NotImplementedError("PostgresStores.get_fills")

    # ---- FeeScheduleStore

    def log_schedule(self, *, schedule: FeeSchedule) -> int:
        raise NotImplementedError("PostgresStores.log_schedule")

    def get_latest(self, *, exchange: str, symbol: str | None = None) -> Optional[FeeSchedule]:
        raise NotImplementedError("PostgresStores.get_latest_fee_schedule")
