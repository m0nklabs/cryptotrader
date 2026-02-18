"""Async CRUD operations for trade history and order audit logging.

Provides database operations for:
- Trade executions (filled orders)
- Order audit log (all order state changes)
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trade Executions
# ---------------------------------------------------------------------------


async def create_trade(
    conn: asyncpg.Connection,
    trade_id: str,
    exchange: str,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    execution_time: datetime,
    order_id: str | None = None,
    fee: Decimal = Decimal("0"),
    fee_currency: str | None = None,
    trade_type: str = "market",
    is_paper: bool = True,
) -> int:
    """Create a trade execution record.

    Args:
        conn: Database connection
        trade_id: Unique trade ID
        exchange: Exchange name
        symbol: Trading symbol
        side: BUY or SELL
        quantity: Trade quantity
        price: Execution price
        execution_time: Trade execution timestamp
        order_id: Associated order ID (optional)
        fee: Trading fee
        fee_currency: Fee currency
        trade_type: Trade type (market, limit, stop)
        is_paper: Whether this is a paper trade

    Returns:
        Trade record ID
    """
    quote_qty = quantity * price

    query = """
        INSERT INTO trades (
            trade_id, order_id, exchange, symbol, side, quantity,
            price, fee, fee_currency, quote_qty, trade_type,
            execution_time, is_paper
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (trade_id) DO NOTHING
        RETURNING id
    """
    record_id = await conn.fetchval(
        query,
        trade_id,
        order_id,
        exchange,
        symbol,
        side,
        quantity,
        price,
        fee,
        fee_currency,
        quote_qty,
        trade_type,
        execution_time,
        is_paper,
    )
    return record_id


async def get_trades(
    conn: asyncpg.Connection,
    symbol: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    is_paper: bool | None = None,
    limit: int = 100,
) -> list[asyncpg.Record]:
    """Get trade execution records.

    Args:
        conn: Database connection
        symbol: Filter by symbol (optional)
        start_time: Start timestamp (optional)
        end_time: End timestamp (optional)
        is_paper: Filter by paper/live trades (optional)
        limit: Maximum number of records

    Returns:
        List of trade records
    """
    conditions = []
    params = []
    param_idx = 1

    if symbol:
        conditions.append(f"symbol = ${param_idx}")
        params.append(symbol)
        param_idx += 1

    if start_time:
        conditions.append(f"execution_time >= ${param_idx}")
        params.append(start_time)
        param_idx += 1

    if end_time:
        conditions.append(f"execution_time <= ${param_idx}")
        params.append(end_time)
        param_idx += 1

    if is_paper is not None:
        conditions.append(f"is_paper = ${param_idx}")
        params.append(is_paper)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.append(limit)

    query = f"""
        SELECT * FROM trades
        WHERE {where_clause}
        ORDER BY execution_time DESC
        LIMIT ${param_idx}
    """

    return await conn.fetch(query, *params)


async def get_trade_by_id(conn: asyncpg.Connection, trade_id: str) -> asyncpg.Record | None:
    """Get a specific trade by trade_id.

    Args:
        conn: Database connection
        trade_id: Trade ID

    Returns:
        Trade record or None
    """
    query = "SELECT * FROM trades WHERE trade_id = $1"
    return await conn.fetchrow(query, trade_id)


# ---------------------------------------------------------------------------
# Order Audit Log
# ---------------------------------------------------------------------------


async def log_order_event(
    conn: asyncpg.Connection,
    order_id: str,
    exchange: str,
    symbol: str,
    side: str,
    order_type: str,
    status: str,
    event_type: str,
    event_time: datetime,
    quantity: Decimal | None = None,
    filled_quantity: Decimal | None = None,
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
    avg_fill_price: Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Log an order state change event.

    Args:
        conn: Database connection
        order_id: Order ID
        exchange: Exchange name
        symbol: Trading symbol
        side: BUY or SELL
        order_type: Order type (market, limit, stop)
        status: Order status
        event_type: Event type (CREATED, FILLED, PARTIAL_FILL, CANCELLED, REJECTED)
        event_time: Event timestamp
        quantity: Order quantity
        filled_quantity: Filled quantity
        limit_price: Limit price
        stop_price: Stop price
        avg_fill_price: Average fill price
        metadata: Additional context (JSON)

    Returns:
        Log record ID
    """
    query = """
        INSERT INTO order_audit_log (
            order_id, exchange, symbol, side, order_type, status,
            event_type, event_time, quantity, filled_quantity,
            limit_price, stop_price, avg_fill_price, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        RETURNING id
    """
    log_id = await conn.fetchval(
        query,
        order_id,
        exchange,
        symbol,
        side,
        order_type,
        status,
        event_type,
        event_time,
        quantity,
        filled_quantity,
        limit_price,
        stop_price,
        avg_fill_price,
        metadata,
    )
    return log_id


async def get_order_audit_log(
    conn: asyncpg.Connection,
    order_id: str | None = None,
    symbol: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[asyncpg.Record]:
    """Get order audit log records.

    Args:
        conn: Database connection
        order_id: Filter by order ID (optional)
        symbol: Filter by symbol (optional)
        start_time: Start timestamp (optional)
        end_time: End timestamp (optional)
        limit: Maximum number of records

    Returns:
        List of audit log records
    """
    conditions = []
    params = []
    param_idx = 1

    if order_id:
        conditions.append(f"order_id = ${param_idx}")
        params.append(order_id)
        param_idx += 1

    if symbol:
        conditions.append(f"symbol = ${param_idx}")
        params.append(symbol)
        param_idx += 1

    if start_time:
        conditions.append(f"event_time >= ${param_idx}")
        params.append(start_time)
        param_idx += 1

    if end_time:
        conditions.append(f"event_time <= ${param_idx}")
        params.append(end_time)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.append(limit)

    query = f"""
        SELECT * FROM order_audit_log
        WHERE {where_clause}
        ORDER BY event_time DESC
        LIMIT ${param_idx}
    """

    return await conn.fetch(query, *params)
