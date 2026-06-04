"""API endpoints for portfolio tracking and P&L."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
import asyncpg

from db.crud import portfolio as portfolio_crud

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_db_pool: asyncpg.Pool | None = None


async def _get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool."""
    global _db_pool
    if _db_pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL is not set")
        # Normalize URL for asyncpg (remove +asyncpg suffix if present)
        if "+asyncpg" in database_url:
            database_url = database_url.replace("+asyncpg", "")
        _db_pool = await asyncpg.create_pool(database_url)
    return _db_pool


# ---------------------------------------------------------------------------
# Portfolio Snapshots
# ---------------------------------------------------------------------------


@router.get("/snapshots")
async def get_snapshots(
    start_time: str | None = Query(None, description="Start timestamp (ISO 8601)"),
    end_time: str | None = Query(None, description="End timestamp (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of snapshots"),
) -> dict[str, Any]:
    """Get portfolio snapshots for equity curve.

    Returns snapshots of portfolio state over time including:
    - Total equity
    - Cash balance
    - Position value
    - Unrealized/realized P&L
    """
    pool = await _get_db_pool()

    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None

    async with pool.acquire() as conn:
        snapshots = await portfolio_crud.get_portfolio_snapshots(
            conn, start_time=start_dt, end_time=end_dt, limit=limit
        )

    return {
        "snapshots": [
            {
                "id": row["id"],
                "timestamp": row["timestamp"].isoformat(),
                "total_equity": str(row["total_equity"]),
                "cash_balance": str(row["cash_balance"]),
                "position_value": str(row["position_value"]),
                "unrealized_pnl": str(row["unrealized_pnl"]),
                "realized_pnl": str(row["realized_pnl"]),
                "total_pnl": str(row["total_pnl"]),
                "quote_currency": row["quote_currency"],
            }
            for row in snapshots
        ]
    }


@router.get("/snapshots/latest")
async def get_latest_snapshot() -> dict[str, Any]:
    """Get the most recent portfolio snapshot."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        snapshot = await portfolio_crud.get_latest_portfolio_snapshot(conn)

    if not snapshot:
        raise HTTPException(status_code=404, detail="No portfolio snapshots found")

    return {
        "snapshot": {
            "id": snapshot["id"],
            "timestamp": snapshot["timestamp"].isoformat(),
            "total_equity": str(snapshot["total_equity"]),
            "cash_balance": str(snapshot["cash_balance"]),
            "position_value": str(snapshot["position_value"]),
            "unrealized_pnl": str(snapshot["unrealized_pnl"]),
            "realized_pnl": str(snapshot["realized_pnl"]),
            "total_pnl": str(snapshot["total_pnl"]),
            "quote_currency": snapshot["quote_currency"],
        }
    }


@router.post("/snapshots")
async def create_snapshot(
    total_equity: str,
    cash_balance: str,
    position_value: str,
    unrealized_pnl: str,
    realized_pnl: str,
    total_pnl: str,
    quote_currency: str = "USDT",
) -> dict[str, Any]:
    """Create a new portfolio snapshot.

    This endpoint allows manual creation of snapshots for testing
    or integration with external systems.
    """
    pool = await _get_db_pool()

    try:
        total_equity_dec = Decimal(total_equity)
        cash_balance_dec = Decimal(cash_balance)
        position_value_dec = Decimal(position_value)
        unrealized_pnl_dec = Decimal(unrealized_pnl)
        realized_pnl_dec = Decimal(realized_pnl)
        total_pnl_dec = Decimal(total_pnl)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid decimal value: {e}")

    timestamp = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        snapshot_id = await portfolio_crud.create_portfolio_snapshot(
            conn,
            timestamp=timestamp,
            total_equity=total_equity_dec,
            cash_balance=cash_balance_dec,
            position_value=position_value_dec,
            unrealized_pnl=unrealized_pnl_dec,
            realized_pnl=realized_pnl_dec,
            total_pnl=total_pnl_dec,
            quote_currency=quote_currency,
        )

    return {
        "success": True,
        "snapshot_id": snapshot_id,
        "timestamp": timestamp.isoformat(),
    }


# ---------------------------------------------------------------------------
# Position History
# ---------------------------------------------------------------------------


@router.get("/positions/history")
async def get_position_history(
    symbol: str | None = Query(None, description="Filter by symbol"),
    start_time: str | None = Query(None, description="Start timestamp (ISO 8601)"),
    end_time: str | None = Query(None, description="End timestamp (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
) -> dict[str, Any]:
    """Get position history for audit trail.

    Returns historical snapshots of positions over time.
    """
    pool = await _get_db_pool()

    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None

    async with pool.acquire() as conn:
        history = await portfolio_crud.get_position_history(
            conn, symbol=symbol, start_time=start_dt, end_time=end_dt, limit=limit
        )

    return {
        "history": [
            {
                "id": row["id"],
                "timestamp": row["timestamp"].isoformat(),
                "symbol": row["symbol"],
                "exchange": row["exchange"],
                "quantity": str(row["quantity"]),
                "avg_entry_price": str(row["avg_entry_price"]),
                "current_price": str(row["current_price"]),
                "unrealized_pnl": str(row["unrealized_pnl"]),
                "realized_pnl": str(row["realized_pnl"]),
                "cost_basis": row["cost_basis"],
            }
            for row in history
        ]
    }


# ---------------------------------------------------------------------------
# Balance Snapshots
# ---------------------------------------------------------------------------


@router.get("/balances/history")
async def get_balance_history(
    exchange: str | None = Query(None, description="Filter by exchange"),
    currency: str | None = Query(None, description="Filter by currency"),
    start_time: str | None = Query(None, description="Start timestamp (ISO 8601)"),
    end_time: str | None = Query(None, description="End timestamp (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
) -> dict[str, Any]:
    """Get balance history over time.

    Returns historical snapshots of exchange balances.
    """
    pool = await _get_db_pool()

    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None

    async with pool.acquire() as conn:
        history = await portfolio_crud.get_balance_snapshots(
            conn,
            exchange=exchange,
            currency=currency,
            start_time=start_dt,
            end_time=end_dt,
            limit=limit,
        )

    return {
        "history": [
            {
                "id": row["id"],
                "timestamp": row["timestamp"].isoformat(),
                "exchange": row["exchange"],
                "currency": row["currency"],
                "available": str(row["available"]),
                "reserved": str(row["reserved"]),
                "total": str(row["total"]),
            }
            for row in history
        ]
    }
