from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Mapping, Optional, Sequence

Timeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]
SignalSide = Literal["BUY", "SELL", "HOLD", "CONFIRM"]


@dataclass(frozen=True)
class Candle:
    symbol: str
    exchange: str
    timeframe: Timeframe
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class IndicatorSignal:
    code: str
    side: SignalSide
    strength: int  # 0-100
    value: str
    reason: str


@dataclass(frozen=True)
class Opportunity:
    symbol: str
    timeframe: Timeframe
    score: int  # 0-100
    side: SignalSide
    signals: tuple[IndicatorSignal, ...]


@dataclass(frozen=True)
class FeeBreakdown:
    currency: str
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    assumed_spread_bps: int
    assumed_slippage_bps: int


@dataclass(frozen=True)
class CostEstimate:
    fee_currency: str
    gross_notional: Decimal
    estimated_fees: Decimal
    estimated_spread_cost: Decimal
    estimated_slippage_cost: Decimal
    estimated_total_cost: Decimal
    minimum_edge_rate: Decimal
    minimum_edge_bps: Decimal


@dataclass(frozen=True)
class OrderIntent:
    exchange: str
    symbol: str
    side: Literal["BUY", "SELL"]
    amount: Decimal
    order_type: Literal["market", "limit"] = "market"
    limit_price: Optional[Decimal] = None
    metadata: Mapping[str, str] = None


@dataclass(frozen=True)
class ExecutionResult:
    dry_run: bool
    accepted: bool
    reason: str
    order_id: Optional[str] = None
    raw: Optional[Mapping[str, object]] = None


@dataclass(frozen=True)
class Exchange:
    code: str
    name: Optional[str] = None
    is_active: bool = True


@dataclass(frozen=True)
class Symbol:
    exchange_code: Optional[str]
    symbol: str
    base_asset: Optional[str] = None
    quote_asset: Optional[str] = None
    is_active: bool = True


@dataclass(frozen=True)
class Strategy:
    name: str
    description: Optional[str] = None
    is_active: bool = True


MarketDataJobType = Literal["backfill", "realtime", "repair"]
MarketDataJobStatus = Literal["created", "running", "success", "failed"]


@dataclass(frozen=True)
class MarketDataJob:
    job_type: MarketDataJobType
    exchange: str
    symbol: str
    timeframe: Timeframe
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: MarketDataJobStatus = "created"
    last_error: Optional[str] = None


@dataclass(frozen=True)
class MarketDataJobRun:
    job_id: int
    started_at: datetime
    finished_at: Optional[datetime]
    status: MarketDataJobStatus
    candles_fetched: int = 0
    candles_upserted: int = 0
    last_open_time: Optional[datetime] = None
    last_error: Optional[str] = None


@dataclass(frozen=True)
class CandleGap:
    exchange: str
    symbol: str
    timeframe: Timeframe
    expected_open_time: datetime
    expected_close_time: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    repaired_at: Optional[datetime] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class WalletSnapshot:
    exchange: str
    currency: str
    balance: Decimal
    wallet_type: Optional[str] = None
    available_balance: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    raw_json: Optional[str] = None


@dataclass(frozen=True)
class PositionSnapshot:
    exchange: str
    symbol: str
    side: Literal["long", "short"]
    amount: Decimal
    entry_price: Optional[Decimal] = None
    mark_price: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    raw_json: Optional[str] = None


@dataclass(frozen=True)
class OrderRecord:
    exchange: str
    symbol: str
    side: Literal["BUY", "SELL"]
    order_type: Literal["market", "limit"]
    amount: Decimal
    order_id: Optional[str] = None
    price: Optional[Decimal] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    raw_json: Optional[str] = None


@dataclass(frozen=True)
class TradeFill:
    exchange: str
    symbol: str
    side: Literal["BUY", "SELL"]
    amount: Decimal
    price: Decimal
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    fee_currency: Optional[str] = None
    fee_amount: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    raw_json: Optional[str] = None


@dataclass(frozen=True)
class FeeSchedule:
    exchange: str
    symbol: Optional[str] = None
    maker_fee_rate: Optional[Decimal] = None
    taker_fee_rate: Optional[Decimal] = None
    assumed_spread_bps: Optional[int] = None
    assumed_slippage_bps: Optional[int] = None
    notes: Optional[str] = None
    raw_json: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    message: str
    severity: Literal["debug", "info", "warning", "error"] = "info"
    event_time: Optional[datetime] = None
    context_json: Optional[str] = None


@dataclass(frozen=True)
class OpportunitySnapshot:
    symbol: str
    timeframe: Timeframe
    score: int
    side: SignalSide
    exchange: Optional[str] = None
    signals: Sequence[IndicatorSignal] = ()
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class AutomationRule:
    rule_type: str
    value: Mapping[str, object]
    symbol: Optional[str] = None
    is_active: bool = True
    id: Optional[int] = None
    created_at: Optional[datetime] = None


DecisionType = Literal["EXECUTE", "REJECT", "SKIP"]


@dataclass(frozen=True)
class AuditLogEntry:
    event_type: str
    decision: Optional[DecisionType] = None
    symbol: Optional[str] = None
    reason: Optional[str] = None
    context: Optional[Mapping[str, object]] = None
    created_at: Optional[datetime] = None
    id: Optional[int] = None
