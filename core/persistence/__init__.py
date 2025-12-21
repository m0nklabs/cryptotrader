"""Optional persistence interfaces.

These protocols define the persistence boundary. Implementations can be backed by
PostgreSQL (recommended) or other stores.

Authoritative requirements live in docs/.
"""

from .interfaces import (
    AuditEventStore,
    CandleStore,
    CandleGapStore,
    ExecutionStore,
    ExchangeStore,
    FeeScheduleStore,
    MarketDataJobRunStore,
    MarketDataJobStore,
    OrderStore,
    OpportunityStore,
    PositionStore,
    StrategyStore,
    SymbolStore,
    TradeFillStore,
    WalletSnapshotStore,
)
