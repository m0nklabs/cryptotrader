"""API routes for rate limit status."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from core.ratelimit import get_tracker

router = APIRouter(prefix="/ratelimit", tags=["ratelimit"])


@router.get("/status")
async def get_rate_limit_status(
    exchange: Optional[str] = Query(None, description="Filter by exchange"),
):
    """Get rate limit status for all exchanges or a specific exchange.

    Returns current rate limit usage, remaining quota, and reset times.
    """
    tracker = get_tracker()

    # Clean up expired entries
    tracker.clear_expired()

    # Get all rate limit info
    limits = tracker.get_all(exchange=exchange)

    # Convert to dict format
    result = []
    for limit_info in limits:
        result.append(
            {
                "exchange": limit_info.exchange,
                "endpoint": limit_info.endpoint,
                "limit": limit_info.limit,
                "used": limit_info.used,
                "remaining": limit_info.remaining,
                "usage_percent": round(limit_info.usage_percent, 2),
                "reset_at": limit_info.reset_at,
                "reset_in_seconds": limit_info.reset_in_seconds,
                "status": limit_info.status,
                "window_seconds": limit_info.window_seconds,
            }
        )

    return {
        "limits": result,
        "count": len(result),
    }


@router.get("/exchanges")
async def get_exchanges():
    """Get list of exchanges with rate limit tracking."""
    tracker = get_tracker()
    limits = tracker.get_all()

    # Extract unique exchanges
    exchanges = sorted(set(limit.exchange for limit in limits))

    return {"exchanges": exchanges, "count": len(exchanges)}
