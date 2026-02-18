"""Async CRUD operations for watchlist tables.

Provides database operations for:
- Watchlists (named symbol lists)
- Watchlist items (symbols within lists)
- Column preferences (configurable display columns)
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Watchlists
# ---------------------------------------------------------------------------


async def create_watchlist(
    conn: asyncpg.Connection,
    name: str,
    description: str | None = None,
    is_default: bool = False,
) -> int:
    """Create a new watchlist.

    Args:
        conn: Database connection
        name: Watchlist name
        description: Optional description
        is_default: Whether this is the default watchlist

    Returns:
        Watchlist ID
    """
    query = """
        INSERT INTO watchlists (name, description, is_default)
        VALUES ($1, $2, $3)
        RETURNING id
    """
    watchlist_id = await conn.fetchval(query, name, description, is_default)
    return watchlist_id


async def get_watchlists(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Get all watchlists ordered by sort_order.

    Args:
        conn: Database connection

    Returns:
        List of watchlist records
    """
    query = """
        SELECT * FROM watchlists
        ORDER BY sort_order, id
    """
    return await conn.fetch(query)


async def get_watchlist(conn: asyncpg.Connection, watchlist_id: int) -> asyncpg.Record | None:
    """Get a specific watchlist by ID.

    Args:
        conn: Database connection
        watchlist_id: Watchlist ID

    Returns:
        Watchlist record or None
    """
    query = "SELECT * FROM watchlists WHERE id = $1"
    return await conn.fetchrow(query, watchlist_id)


async def update_watchlist(
    conn: asyncpg.Connection,
    watchlist_id: int,
    name: str | None = None,
    description: str | None = None,
    is_default: bool | None = None,
) -> bool:
    """Update a watchlist.

    Args:
        conn: Database connection
        watchlist_id: Watchlist ID
        name: New name (optional)
        description: New description (optional)
        is_default: New default status (optional)

    Returns:
        True if updated successfully
    """
    updates = []
    params = []
    param_idx = 1

    if name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(name)
        param_idx += 1

    if description is not None:
        updates.append(f"description = ${param_idx}")
        params.append(description)
        param_idx += 1

    if is_default is not None:
        updates.append(f"is_default = ${param_idx}")
        params.append(is_default)
        param_idx += 1

    if not updates:
        return False

    updates.append("updated_at = NOW()")
    params.append(watchlist_id)

    query = f"""
        UPDATE watchlists
        SET {", ".join(updates)}
        WHERE id = ${param_idx}
    """

    result = await conn.execute(query, *params)
    return result == "UPDATE 1"


async def delete_watchlist(conn: asyncpg.Connection, watchlist_id: int) -> bool:
    """Delete a watchlist and its items.

    Args:
        conn: Database connection
        watchlist_id: Watchlist ID

    Returns:
        True if deleted successfully
    """
    query = "DELETE FROM watchlists WHERE id = $1"
    result = await conn.execute(query, watchlist_id)
    return result == "DELETE 1"


# ---------------------------------------------------------------------------
# Watchlist Items
# ---------------------------------------------------------------------------


async def add_watchlist_item(
    conn: asyncpg.Connection,
    watchlist_id: int,
    exchange: str,
    symbol: str,
    notes: str | None = None,
) -> int:
    """Add a symbol to a watchlist.

    Args:
        conn: Database connection
        watchlist_id: Watchlist ID
        exchange: Exchange name
        symbol: Trading symbol
        notes: Optional notes

    Returns:
        Item ID
    """
    # Get max sort order for this watchlist
    max_order = await conn.fetchval(
        "SELECT COALESCE(MAX(sort_order), -1) FROM watchlist_items WHERE watchlist_id = $1",
        watchlist_id,
    )
    new_order = (max_order or -1) + 1

    query = """
        INSERT INTO watchlist_items (watchlist_id, exchange, symbol, notes, sort_order)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (watchlist_id, exchange, symbol) DO NOTHING
        RETURNING id
    """
    item_id = await conn.fetchval(query, watchlist_id, exchange, symbol, notes, new_order)
    return item_id


async def get_watchlist_items(conn: asyncpg.Connection, watchlist_id: int) -> list[asyncpg.Record]:
    """Get all items in a watchlist.

    Args:
        conn: Database connection
        watchlist_id: Watchlist ID

    Returns:
        List of watchlist item records
    """
    query = """
        SELECT * FROM watchlist_items
        WHERE watchlist_id = $1
        ORDER BY sort_order
    """
    return await conn.fetch(query, watchlist_id)


async def remove_watchlist_item(conn: asyncpg.Connection, item_id: int) -> bool:
    """Remove an item from a watchlist.

    Args:
        conn: Database connection
        item_id: Item ID

    Returns:
        True if removed successfully
    """
    query = "DELETE FROM watchlist_items WHERE id = $1"
    result = await conn.execute(query, item_id)
    return result == "DELETE 1"


async def update_watchlist_item_order(conn: asyncpg.Connection, item_id: int, sort_order: int) -> bool:
    """Update the sort order of a watchlist item.

    Args:
        conn: Database connection
        item_id: Item ID
        sort_order: New sort order

    Returns:
        True if updated successfully
    """
    query = "UPDATE watchlist_items SET sort_order = $1 WHERE id = $2"
    result = await conn.execute(query, sort_order, item_id)
    return result == "UPDATE 1"


# ---------------------------------------------------------------------------
# Column Preferences
# ---------------------------------------------------------------------------


async def set_column_preference(
    conn: asyncpg.Connection,
    watchlist_id: int,
    column_name: str,
    is_visible: bool = True,
    sort_order: int | None = None,
    width: int | None = None,
) -> int:
    """Set column preference for a watchlist.

    Args:
        conn: Database connection
        watchlist_id: Watchlist ID
        column_name: Column name
        is_visible: Whether column is visible
        sort_order: Column sort order
        width: Column width in pixels

    Returns:
        Preference ID
    """
    if sort_order is None:
        max_order = await conn.fetchval(
            "SELECT COALESCE(MAX(sort_order), -1) FROM watchlist_column_prefs WHERE watchlist_id = $1",
            watchlist_id,
        )
        sort_order = (max_order or -1) + 1

    query = """
        INSERT INTO watchlist_column_prefs (
            watchlist_id, column_name, is_visible, sort_order, width
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (watchlist_id, column_name)
        DO UPDATE SET
            is_visible = EXCLUDED.is_visible,
            sort_order = EXCLUDED.sort_order,
            width = EXCLUDED.width
        RETURNING id
    """
    pref_id = await conn.fetchval(query, watchlist_id, column_name, is_visible, sort_order, width)
    return pref_id


async def get_column_preferences(conn: asyncpg.Connection, watchlist_id: int) -> list[asyncpg.Record]:
    """Get column preferences for a watchlist.

    Args:
        conn: Database connection
        watchlist_id: Watchlist ID

    Returns:
        List of column preference records
    """
    query = """
        SELECT * FROM watchlist_column_prefs
        WHERE watchlist_id = $1
        ORDER BY sort_order
    """
    return await conn.fetch(query, watchlist_id)


async def delete_column_preference(conn: asyncpg.Connection, pref_id: int) -> bool:
    """Delete a column preference.

    Args:
        conn: Database connection
        pref_id: Preference ID

    Returns:
        True if deleted successfully
    """
    query = "DELETE FROM watchlist_column_prefs WHERE id = $1"
    result = await conn.execute(query, pref_id)
    return result == "DELETE 1"
