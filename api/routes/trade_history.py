"""API endpoints for trade history and order audit logging."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
import asyncpg

from db.crud import trade_history as trade_crud

router = APIRouter(prefix="/trades", tags=["trades"])

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
# Trade Executions
# ---------------------------------------------------------------------------


@router.get("/")
async def list_trades(
    symbol: str | None = Query(None, description="Filter by symbol"),
    start_time: str | None = Query(None, description="Start timestamp (ISO 8601)"),
    end_time: str | None = Query(None, description="End timestamp (ISO 8601)"),
    is_paper: bool | None = Query(None, description="Filter by paper/live trades"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of trades"),
) -> dict[str, Any]:
    """List trade executions with optional filters.
    
    Returns completed trade fills with P&L details.
    """
    pool = await _get_db_pool()
    
    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None
    
    async with pool.acquire() as conn:
        trades = await trade_crud.get_trades(
            conn,
            symbol=symbol,
            start_time=start_dt,
            end_time=end_dt,
            is_paper=is_paper,
            limit=limit,
        )
    
    return {
        "trades": [
            {
                "id": row["id"],
                "trade_id": row["trade_id"],
                "order_id": row["order_id"],
                "exchange": row["exchange"],
                "symbol": row["symbol"],
                "side": row["side"],
                "quantity": str(row["quantity"]),
                "price": str(row["price"]),
                "fee": str(row["fee"]),
                "fee_currency": row["fee_currency"],
                "quote_qty": str(row["quote_qty"]),
                "trade_type": row["trade_type"],
                "execution_time": row["execution_time"].isoformat(),
                "is_paper": row["is_paper"],
            }
            for row in trades
        ]
    }


@router.get("/{trade_id}")
async def get_trade(trade_id: str) -> dict[str, Any]:
    """Get a specific trade by trade_id."""
    pool = await _get_db_pool()
    
    async with pool.acquire() as conn:
        trade = await trade_crud.get_trade_by_id(conn, trade_id)
    
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    return {
        "trade": {
            "id": trade["id"],
            "trade_id": trade["trade_id"],
            "order_id": trade["order_id"],
            "exchange": trade["exchange"],
            "symbol": trade["symbol"],
            "side": trade["side"],
            "quantity": str(trade["quantity"]),
            "price": str(trade["price"]),
            "fee": str(trade["fee"]),
            "fee_currency": trade["fee_currency"],
            "quote_qty": str(trade["quote_qty"]),
            "trade_type": trade["trade_type"],
            "execution_time": trade["execution_time"].isoformat(),
            "is_paper": trade["is_paper"],
        }
    }


@router.post("/")
async def create_trade(
    trade_id: str,
    exchange: str,
    symbol: str,
    side: str,
    quantity: str,
    price: str,
    execution_time: str,
    order_id: str | None = None,
    fee: str = "0",
    fee_currency: str | None = None,
    trade_type: str = "market",
    is_paper: bool = True,
) -> dict[str, Any]:
    """Create a trade execution record.
    
    This endpoint allows manual creation of trade records for testing
    or integration with external systems.
    """
    pool = await _get_db_pool()
    
    try:
        quantity_dec = Decimal(quantity)
        price_dec = Decimal(price)
        fee_dec = Decimal(fee)
        execution_dt = datetime.fromisoformat(execution_time)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {e}")
    
    async with pool.acquire() as conn:
        record_id = await trade_crud.create_trade(
            conn,
            trade_id=trade_id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            quantity=quantity_dec,
            price=price_dec,
            execution_time=execution_dt,
            order_id=order_id,
            fee=fee_dec,
            fee_currency=fee_currency,
            trade_type=trade_type,
            is_paper=is_paper,
        )
    
    if not record_id:
        raise HTTPException(status_code=409, detail="Trade ID already exists")
    
    return {
        "success": True,
        "trade_record_id": record_id,
    }


# ---------------------------------------------------------------------------
# Order Audit Log
# ---------------------------------------------------------------------------


@router.get("/audit")
async def get_audit_log(
    order_id: str | None = Query(None, description="Filter by order ID"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    start_time: str | None = Query(None, description="Start timestamp (ISO 8601)"),
    end_time: str | None = Query(None, description="End timestamp (ISO 8601)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
) -> dict[str, Any]:
    """Get order audit log with optional filters.
    
    Returns all order state change events for compliance and debugging.
    """
    pool = await _get_db_pool()
    
    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None
    
    async with pool.acquire() as conn:
        logs = await trade_crud.get_order_audit_log(
            conn,
            order_id=order_id,
            symbol=symbol,
            start_time=start_dt,
            end_time=end_dt,
            limit=limit,
        )
    
    return {
        "audit_log": [
            {
                "id": row["id"],
                "order_id": row["order_id"],
                "exchange": row["exchange"],
                "symbol": row["symbol"],
                "side": row["side"],
                "order_type": row["order_type"],
                "status": row["status"],
                "event_type": row["event_type"],
                "event_time": row["event_time"].isoformat(),
                "quantity": str(row["quantity"]) if row["quantity"] else None,
                "filled_quantity": str(row["filled_quantity"]) if row["filled_quantity"] else None,
                "limit_price": str(row["limit_price"]) if row["limit_price"] else None,
                "stop_price": str(row["stop_price"]) if row["stop_price"] else None,
                "avg_fill_price": str(row["avg_fill_price"]) if row["avg_fill_price"] else None,
                "metadata": row["metadata"],
            }
            for row in logs
        ]
    }


@router.post("/audit")
async def log_order_event(
    order_id: str,
    exchange: str,
    symbol: str,
    side: str,
    order_type: str,
    status: str,
    event_type: str,
    event_time: str,
    quantity: str | None = None,
    filled_quantity: str | None = None,
    limit_price: str | None = None,
    stop_price: str | None = None,
    avg_fill_price: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log an order state change event."""
    pool = await _get_db_pool()
    
    try:
        event_dt = datetime.fromisoformat(event_time)
        quantity_dec = Decimal(quantity) if quantity else None
        filled_quantity_dec = Decimal(filled_quantity) if filled_quantity else None
        limit_price_dec = Decimal(limit_price) if limit_price else None
        stop_price_dec = Decimal(stop_price) if stop_price else None
        avg_fill_price_dec = Decimal(avg_fill_price) if avg_fill_price else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {e}")
    
    async with pool.acquire() as conn:
        log_id = await trade_crud.log_order_event(
            conn,
            order_id=order_id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            order_type=order_type,
            status=status,
            event_type=event_type,
            event_time=event_dt,
            quantity=quantity_dec,
            filled_quantity=filled_quantity_dec,
            limit_price=limit_price_dec,
            stop_price=stop_price_dec,
            avg_fill_price=avg_fill_price_dec,
            metadata=metadata,
        )
    
    return {
        "success": True,
        "log_id": log_id,
    }
