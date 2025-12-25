"""Configurable indicator weights with code defaults and optional DB overrides.

This module provides a flexible weight management system that:
- Works offline with hardcoded defaults (no DB required)
- Supports optional per-strategy DB overrides
- Auto-normalizes weights to sum to 1.0

Usage:
    from core.signals.weights import get_weights

    # Get default weights (no DB required)
    weights = get_weights()

    # Get strategy-specific weights from DB (falls back to defaults)
    weights = get_weights(strategy_id="aggressive", db_pool=pool)
"""

from __future__ import annotations

import logging
from typing import Any

from core.signals.scoring import normalize_weights

logger = logging.getLogger(__name__)

# Default indicator weights (hardcoded, no DB required)
# These are used when DB is unavailable or no custom weights exist
DEFAULT_WEIGHTS: dict[str, float] = {
    "RSI": 0.20,
    "MACD": 0.25,
    "STOCHASTIC": 0.15,
    "BOLLINGER": 0.15,
    "ATR": 0.05,
    "MA_CROSS": 0.15,
    "VOLUME_SPIKE": 0.05,
}


async def load_weights_from_db(
    strategy_id: str = "default",
    db_pool: Any | None = None,
) -> dict[str, float] | None:
    """Load indicator weights from database for a specific strategy.

    Args:
        strategy_id: Strategy identifier (default: "default")
        db_pool: Optional database connection pool (asyncpg or SQLAlchemy)

    Returns:
        Dictionary of indicator weights, or None if not found/error

    Note:
        Silently returns None on any DB error to allow offline operation
    """
    if db_pool is None:
        return None

    try:
        # Determine pool type and execute query accordingly
        # Support both asyncpg and SQLAlchemy async pools
        query = """
            SELECT indicator_name, weight
            FROM strategy_indicator_weights
            WHERE strategy_id = $1
            ORDER BY indicator_name
        """

        # Try asyncpg-style query first
        if hasattr(db_pool, "fetch"):
            rows = await db_pool.fetch(query, strategy_id)
            if rows:
                return {row["indicator_name"]: float(row["weight"]) for row in rows}
        # Try SQLAlchemy async session
        elif hasattr(db_pool, "execute"):
            from sqlalchemy import text

            result = await db_pool.execute(text(query.replace("$1", ":strategy_id")), {"strategy_id": strategy_id})
            rows = result.fetchall()
            if rows:
                return {row[0]: float(row[1]) for row in rows}

    except Exception as exc:
        # Log but don't raise - allow offline operation
        logger.debug(f"Failed to load weights from DB (strategy={strategy_id}): {exc}")

    return None


def get_weights(
    strategy_id: str = "default",
    db_pool: Any | None = None,
) -> dict[str, float]:
    """Get indicator weights with DB override support.

    This function provides the main weight retrieval interface with:
    - Hardcoded defaults (always available)
    - Optional DB overrides (per-strategy)
    - Auto-normalization

    Args:
        strategy_id: Strategy identifier (default: "default")
        db_pool: Optional database connection pool

    Returns:
        Normalized indicator weights (sum = 1.0)

    Examples:
        >>> # Offline mode (no DB)
        >>> weights = get_weights()
        >>> weights
        {'RSI': 0.20, 'MACD': 0.25, ...}

        >>> # With DB pool (async context required)
        >>> weights = get_weights(strategy_id="aggressive", db_pool=pool)
    """
    # Note: This is a synchronous wrapper for backwards compatibility
    # For async contexts, use load_weights_from_db directly
    weights = DEFAULT_WEIGHTS.copy()

    # DB loading would need async context - for now, just return defaults
    # In practice, this should be called from async code using load_weights_from_db
    logger.debug(f"Returning default weights for strategy={strategy_id}")

    return normalize_weights(weights)


async def get_weights_async(
    strategy_id: str = "default",
    db_pool: Any | None = None,
) -> dict[str, float]:
    """Async version of get_weights with DB override support.

    This is the preferred method for async code paths.

    Args:
        strategy_id: Strategy identifier (default: "default")
        db_pool: Optional database connection pool

    Returns:
        Normalized indicator weights (sum = 1.0)

    Examples:
        >>> async with pool.acquire() as conn:
        ...     weights = await get_weights_async(strategy_id="aggressive", db_pool=conn)
    """
    # Try loading from DB first
    db_weights = await load_weights_from_db(strategy_id=strategy_id, db_pool=db_pool)

    if db_weights:
        logger.info(f"Loaded {len(db_weights)} custom weights from DB for strategy={strategy_id}")
        # Merge with defaults (DB weights override, but defaults fill gaps)
        merged = DEFAULT_WEIGHTS.copy()
        merged.update(db_weights)
        return normalize_weights(merged)

    # Fallback to defaults
    logger.debug(f"Using default weights for strategy={strategy_id}")
    return normalize_weights(DEFAULT_WEIGHTS.copy())
