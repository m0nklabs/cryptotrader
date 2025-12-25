"""Tests for database schema validation."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_schema_file_exists():
    """Test that the schema.sql file exists."""
    schema_path = ROOT / "db" / "schema.sql"
    assert schema_path.exists(), "db/schema.sql should exist"
    assert schema_path.is_file(), "db/schema.sql should be a file"


def test_schema_contains_required_tables():
    """Test that the schema contains all required tables."""
    schema_path = ROOT / "db" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    # Required tables from the issue
    required_tables = [
        "candles",
        "opportunities",
        "paper_orders",  # Execution/orders for paper trading
        "audit_events",  # Audit log
        "portfolio_snapshots",  # Portfolio snapshots
    ]

    for table_name in required_tables:
        assert (
            f"CREATE TABLE IF NOT EXISTS {table_name}" in schema_sql
        ), f"Schema should contain {table_name} table"


def test_schema_is_idempotent():
    """Test that all CREATE statements use IF NOT EXISTS."""
    schema_path = ROOT / "db" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    # Find all CREATE TABLE statements
    lines = schema_sql.split("\n")
    create_table_lines = [line for line in lines if line.strip().startswith("CREATE TABLE")]

    assert len(create_table_lines) > 0, "Schema should contain CREATE TABLE statements"

    for line in create_table_lines:
        assert "IF NOT EXISTS" in line, f"CREATE TABLE should use IF NOT EXISTS: {line}"


def test_schema_has_indexes():
    """Test that the schema defines indexes for key lookup patterns."""
    schema_path = ROOT / "db" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    # Check for index creation statements
    assert "CREATE INDEX" in schema_sql, "Schema should define indexes"
    assert "IF NOT EXISTS" in schema_sql, "Index creation should be idempotent"


def test_schema_has_transaction():
    """Test that the schema is wrapped in a transaction."""
    schema_path = ROOT / "db" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    assert "BEGIN;" in schema_sql, "Schema should start with BEGIN"
    assert "COMMIT;" in schema_sql, "Schema should end with COMMIT"


def test_init_db_script_exists():
    """Test that the init_db.py script exists."""
    init_db_path = ROOT / "db" / "init_db.py"
    assert init_db_path.exists(), "db/init_db.py should exist"
    assert init_db_path.is_file(), "db/init_db.py should be a file"


def test_init_db_script_can_be_imported():
    """Test that the init_db module can be imported."""
    from db import init_db

    assert hasattr(init_db, "main"), "init_db should have a main function"


def test_persistence_protocols_can_be_imported():
    """Test that all persistence protocols can be imported."""
    from core.persistence import (
        AuditEventStore,
        CandleGapStore,
        CandleStore,
        ExecutionStore,
        ExchangeStore,
        FeeScheduleStore,
        MarketDataJobRunStore,
        MarketDataJobStore,
        OpportunityStore,
        OrderStore,
        PaperOrderStore,
        PaperPositionStore,
        PortfolioSnapshotStore,
        PositionStore,
        StrategyStore,
        SymbolStore,
        TradeFillStore,
        WalletSnapshotStore,
    )

    # Verify these are Protocol types by checking for required methods
    protocols = [
        (CandleStore, "upsert_candles"),
        (OpportunityStore, "log_opportunity"),
        (AuditEventStore, "log_event"),
        (PaperOrderStore, "create_order"),
        (PaperPositionStore, "upsert_position"),
        (PortfolioSnapshotStore, "log_snapshot"),
        (CandleGapStore, "log_gap"),
        (ExecutionStore, "log_intent"),
        (ExchangeStore, "upsert_exchanges"),
        (FeeScheduleStore, "log_schedule"),
        (MarketDataJobRunStore, "start_run"),
        (MarketDataJobStore, "create_job"),
        (OrderStore, "upsert_order"),
        (PositionStore, "log_snapshot"),
        (StrategyStore, "upsert_strategies"),
        (SymbolStore, "upsert_symbols"),
        (TradeFillStore, "upsert_fill"),
        (WalletSnapshotStore, "log_snapshot"),
    ]

    for protocol, method_name in protocols:
        assert hasattr(protocol, method_name), f"{protocol.__name__} should have {method_name} method"


def test_persistence_types_can_be_imported():
    """Test that all persistence-related types can be imported."""
    from core.types import (
        AuditEvent,
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

    # Basic validation that these are dataclasses
    types_to_check = [
        Candle,
        PaperOrder,
        PaperPosition,
        PortfolioSnapshot,
        AuditEvent,
        CandleGap,
        ExecutionResult,
        Exchange,
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
    ]

    for type_cls in types_to_check:
        assert hasattr(type_cls, "__dataclass_fields__"), f"{type_cls.__name__} should be a dataclass"


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set - skipping actual schema application test",
)
def test_schema_applies_cleanly():
    """Test that the schema can be applied to a database.

    This test requires DATABASE_URL to be set and will only run in CI or when explicitly configured.
    """
    from db.init_db import main

    # Run the schema initialization
    result = main()
    assert result == 0, "Schema initialization should return 0 on success"


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set - skipping idempotency test",
)
def test_schema_is_idempotent_in_database():
    """Test that running the schema twice doesn't fail.

    This test requires DATABASE_URL to be set and will only run in CI or when explicitly configured.
    """
    from db.init_db import main

    # Run schema initialization twice
    result1 = main()
    assert result1 == 0, "First schema initialization should succeed"

    result2 = main()
    assert result2 == 0, "Second schema initialization should succeed (idempotent)"
