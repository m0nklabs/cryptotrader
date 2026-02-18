"""Async CRUD operations for portfolio tracking tables.

Provides database operations for:
- Portfolio snapshots (equity curve)
- Position history (audit trail)
- Balance snapshots (cash over time)
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

import asyncpg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Portfolio Snapshots
# ---------------------------------------------------------------------------


async def create_portfolio_snapshot(
    conn: asyncpg.Connection,
    timestamp: datetime,
    total_equity: Decimal,
    cash_balance: Decimal,
    position_value: Decimal,
    unrealized_pnl: Decimal,
    realized_pnl: Decimal,
    total_pnl: Decimal,
    quote_currency: str = "USDT",
) -> int:
    """Create a new portfolio snapshot.

    Args:
        conn: Database connection
        timestamp: Snapshot timestamp
        total_equity: Total portfolio value
        cash_balance: Available cash
        position_value: Total position value
        unrealized_pnl: Unrealized P&L
        realized_pnl: Realized P&L
        total_pnl: Total P&L
        quote_currency: Quote currency (default: USDT)

    Returns:
        Snapshot ID
    """
    query = """
        INSERT INTO portfolio_snapshots (
            timestamp, total_equity, cash_balance, position_value,
            unrealized_pnl, realized_pnl, total_pnl, quote_currency
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
    """
    snapshot_id = await conn.fetchval(
        query,
        timestamp,
        total_equity,
        cash_balance,
        position_value,
        unrealized_pnl,
        realized_pnl,
        total_pnl,
        quote_currency,
    )
    return snapshot_id


async def get_portfolio_snapshots(
    conn: asyncpg.Connection,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[asyncpg.Record]:
    """Get portfolio snapshots within time range.

    Args:
        conn: Database connection
        start_time: Start timestamp (optional)
        end_time: End timestamp (optional)
        limit: Maximum number of snapshots

    Returns:
        List of snapshot records
    """
    conditions = []
    params = []
    param_idx = 1

    if start_time:
        conditions.append(f"timestamp >= ${param_idx}")
        params.append(start_time)
        param_idx += 1

    if end_time:
        conditions.append(f"timestamp <= ${param_idx}")
        params.append(end_time)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.append(limit)

    query = f"""
        SELECT * FROM portfolio_snapshots
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ${param_idx}
    """

    return await conn.fetch(query, *params)


async def get_latest_portfolio_snapshot(
    conn: asyncpg.Connection,
) -> asyncpg.Record | None:
    """Get the most recent portfolio snapshot.

    Args:
        conn: Database connection

    Returns:
        Latest snapshot record or None
    """
    query = """
        SELECT * FROM portfolio_snapshots
        ORDER BY timestamp DESC
        LIMIT 1
    """
    return await conn.fetchrow(query)


# ---------------------------------------------------------------------------
# Position History
# ---------------------------------------------------------------------------


async def create_position_history(
    conn: asyncpg.Connection,
    timestamp: datetime,
    symbol: str,
    exchange: str,
    quantity: Decimal,
    avg_entry_price: Decimal,
    current_price: Decimal,
    unrealized_pnl: Decimal,
    realized_pnl: Decimal,
    cost_basis: str = "FIFO",
) -> int:
    """Create a position history record.

    Args:
        conn: Database connection
        timestamp: History timestamp
        symbol: Trading symbol
        exchange: Exchange name
        quantity: Position quantity
        avg_entry_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized P&L
        realized_pnl: Realized P&L
        cost_basis: Cost basis method (FIFO, LIFO, average)

    Returns:
        History record ID
    """
    query = """
        INSERT INTO position_history (
            timestamp, symbol, exchange, quantity, avg_entry_price,
            current_price, unrealized_pnl, realized_pnl, cost_basis
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
    """
    history_id = await conn.fetchval(
        query,
        timestamp,
        symbol,
        exchange,
        quantity,
        avg_entry_price,
        current_price,
        unrealized_pnl,
        realized_pnl,
        cost_basis,
    )
    return history_id


async def get_position_history(
    conn: asyncpg.Connection,
    symbol: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[asyncpg.Record]:
    """Get position history records.

    Args:
        conn: Database connection
        symbol: Filter by symbol (optional)
        start_time: Start timestamp (optional)
        end_time: End timestamp (optional)
        limit: Maximum number of records

    Returns:
        List of position history records
    """
    conditions = []
    params = []
    param_idx = 1

    if symbol:
        conditions.append(f"symbol = ${param_idx}")
        params.append(symbol)
        param_idx += 1

    if start_time:
        conditions.append(f"timestamp >= ${param_idx}")
        params.append(start_time)
        param_idx += 1

    if end_time:
        conditions.append(f"timestamp <= ${param_idx}")
        params.append(end_time)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.append(limit)

    query = f"""
        SELECT * FROM position_history
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ${param_idx}
    """

    return await conn.fetch(query, *params)


# ---------------------------------------------------------------------------
# Balance Snapshots
# ---------------------------------------------------------------------------


async def create_balance_snapshot(
    conn: asyncpg.Connection,
    timestamp: datetime,
    exchange: str,
    currency: str,
    available: Decimal,
    reserved: Decimal,
    total: Decimal,
) -> int:
    """Create a balance snapshot record.

    Args:
        conn: Database connection
        timestamp: Snapshot timestamp
        exchange: Exchange name
        currency: Currency code
        available: Available balance
        reserved: Reserved balance
        total: Total balance

    Returns:
        Snapshot ID
    """
    query = """
        INSERT INTO balance_snapshots (
            timestamp, exchange, currency, available, reserved, total
        )
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
    """
    snapshot_id = await conn.fetchval(query, timestamp, exchange, currency, available, reserved, total)
    return snapshot_id


async def get_balance_snapshots(
    conn: asyncpg.Connection,
    exchange: str | None = None,
    currency: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[asyncpg.Record]:
    """Get balance snapshot records.

    Args:
        conn: Database connection
        exchange: Filter by exchange (optional)
        currency: Filter by currency (optional)
        start_time: Start timestamp (optional)
        end_time: End timestamp (optional)
        limit: Maximum number of records

    Returns:
        List of balance snapshot records
    """
    conditions = []
    params = []
    param_idx = 1

    if exchange:
        conditions.append(f"exchange = ${param_idx}")
        params.append(exchange)
        param_idx += 1

    if currency:
        conditions.append(f"currency = ${param_idx}")
        params.append(currency)
        param_idx += 1

    if start_time:
        conditions.append(f"timestamp >= ${param_idx}")
        params.append(start_time)
        param_idx += 1

    if end_time:
        conditions.append(f"timestamp <= ${param_idx}")
        params.append(end_time)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.append(limit)

    query = f"""
        SELECT * FROM balance_snapshots
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT ${param_idx}
    """

    return await conn.fetch(query, *params)
