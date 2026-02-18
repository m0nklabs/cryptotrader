"""API endpoints for watchlist management."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
import asyncpg

from db.crud import watchlist as watchlist_crud

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

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
# Watchlists
# ---------------------------------------------------------------------------


@router.get("/")
async def list_watchlists() -> dict[str, Any]:
    """List all watchlists."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        watchlists = await watchlist_crud.get_watchlists(conn)

    return {
        "watchlists": [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "is_default": row["is_default"],
                "sort_order": row["sort_order"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in watchlists
        ]
    }


@router.post("/")
async def create_watchlist(
    name: str,
    description: str | None = None,
    is_default: bool = False,
) -> dict[str, Any]:
    """Create a new watchlist."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        watchlist_id = await watchlist_crud.create_watchlist(
            conn, name=name, description=description, is_default=is_default
        )

    return {
        "success": True,
        "watchlist_id": watchlist_id,
    }


@router.get("/{watchlist_id}")
async def get_watchlist(watchlist_id: int) -> dict[str, Any]:
    """Get a specific watchlist with its items."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        watchlist = await watchlist_crud.get_watchlist(conn, watchlist_id)
        if not watchlist:
            raise HTTPException(status_code=404, detail="Watchlist not found")

        items = await watchlist_crud.get_watchlist_items(conn, watchlist_id)
        columns = await watchlist_crud.get_column_preferences(conn, watchlist_id)

    return {
        "watchlist": {
            "id": watchlist["id"],
            "name": watchlist["name"],
            "description": watchlist["description"],
            "is_default": watchlist["is_default"],
            "created_at": watchlist["created_at"].isoformat(),
            "updated_at": watchlist["updated_at"].isoformat(),
        },
        "items": [
            {
                "id": row["id"],
                "exchange": row["exchange"],
                "symbol": row["symbol"],
                "sort_order": row["sort_order"],
                "notes": row["notes"],
            }
            for row in items
        ],
        "columns": [
            {
                "id": row["id"],
                "column_name": row["column_name"],
                "is_visible": row["is_visible"],
                "sort_order": row["sort_order"],
                "width": row["width"],
            }
            for row in columns
        ],
    }


@router.patch("/{watchlist_id}")
async def update_watchlist(
    watchlist_id: int,
    name: str | None = None,
    description: str | None = None,
    is_default: bool | None = None,
) -> dict[str, Any]:
    """Update a watchlist."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        success = await watchlist_crud.update_watchlist(
            conn,
            watchlist_id=watchlist_id,
            name=name,
            description=description,
            is_default=is_default,
        )

    if not success:
        raise HTTPException(status_code=404, detail="Watchlist not found or no changes")

    return {"success": True}


@router.delete("/{watchlist_id}")
async def delete_watchlist(watchlist_id: int) -> dict[str, Any]:
    """Delete a watchlist."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        success = await watchlist_crud.delete_watchlist(conn, watchlist_id)

    if not success:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    return {"success": True}


# ---------------------------------------------------------------------------
# Watchlist Items
# ---------------------------------------------------------------------------


@router.post("/{watchlist_id}/items")
async def add_item(
    watchlist_id: int,
    exchange: str,
    symbol: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Add a symbol to a watchlist."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        item_id = await watchlist_crud.add_watchlist_item(
            conn, watchlist_id=watchlist_id, exchange=exchange, symbol=symbol, notes=notes
        )

    if not item_id:
        raise HTTPException(status_code=409, detail="Item already exists in watchlist")

    return {
        "success": True,
        "item_id": item_id,
    }


@router.delete("/items/{item_id}")
async def remove_item(item_id: int) -> dict[str, Any]:
    """Remove an item from a watchlist."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        success = await watchlist_crud.remove_watchlist_item(conn, item_id)

    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"success": True}


@router.patch("/items/{item_id}/order")
async def update_item_order(item_id: int, sort_order: int) -> dict[str, Any]:
    """Update the sort order of a watchlist item."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        success = await watchlist_crud.update_watchlist_item_order(conn, item_id=item_id, sort_order=sort_order)

    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"success": True}


# ---------------------------------------------------------------------------
# Column Preferences
# ---------------------------------------------------------------------------


@router.post("/{watchlist_id}/columns")
async def set_column_preference(
    watchlist_id: int,
    column_name: str,
    is_visible: bool = True,
    sort_order: int | None = None,
    width: int | None = None,
) -> dict[str, Any]:
    """Set column preference for a watchlist."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        pref_id = await watchlist_crud.set_column_preference(
            conn,
            watchlist_id=watchlist_id,
            column_name=column_name,
            is_visible=is_visible,
            sort_order=sort_order,
            width=width,
        )

    return {
        "success": True,
        "preference_id": pref_id,
    }


@router.delete("/columns/{pref_id}")
async def delete_column_preference(pref_id: int) -> dict[str, Any]:
    """Delete a column preference."""
    pool = await _get_db_pool()

    async with pool.acquire() as conn:
        success = await watchlist_crud.delete_column_preference(conn, pref_id)

    if not success:
        raise HTTPException(status_code=404, detail="Preference not found")

    return {"success": True}
