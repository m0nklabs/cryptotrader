"""Storage implementations (future).

This package is reserved for concrete implementations of the persistence
interfaces (e.g., PostgreSQL via SQLAlchemy).

Keeping implementations separate makes delegation easier.
"""

from .noop_stores import (
	NoopAuditEventStore,
	NoopCandleGapStore,
	NoopCandleStore,
	NoopExchangeStore,
	NoopExecutionStore,
	NoopFeeScheduleStore,
	NoopMarketDataJobRunStore,
	NoopMarketDataJobStore,
	NoopOpportunityStore,
	NoopOrderStore,
	NoopPositionStore,
	NoopStrategyStore,
	NoopSymbolStore,
	NoopTradeFillStore,
	NoopWalletSnapshotStore,
)

from .postgres import PostgresConfig, PostgresStores
