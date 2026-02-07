"""Coin Dossier API routes.

Provides endpoints for coin dossier entries — daily LLM-generated
technical analysis narratives per trading pair.

Route ordering: static/literal paths MUST come before parameterized
/{symbol} paths to avoid FastAPI matching "queue" or "latest" as a symbol.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.dossier.queue import get_queue
from core.dossier.service import DossierService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dossier", tags=["dossier"])

# Singleton service (lazy init)
_service: DossierService | None = None


def _get_service() -> DossierService:
    global _service
    if _service is None:
        _service = DossierService()
    return _service


# =======================================================================
# STATIC ROUTES (must come before /{symbol} routes)
# =======================================================================


@router.get("/symbols")
async def list_dossier_symbols(
    exchange: str = Query("bitfinex", description="Exchange code"),
):
    """List all symbols that have dossier entries (or available for generation)."""
    svc = _get_service()
    symbols = await svc.get_available_symbols(exchange)
    return {"exchange": exchange, "symbols": symbols}


@router.get("/latest")
async def get_latest_dossiers(
    exchange: str = Query("bitfinex", description="Exchange code"),
    compact: bool = Query(False, description="Return a compact payload (omit large narrative fields)"),
):
    """Get the most recent dossier entry for each coin on the exchange."""
    svc = _get_service()
    entries = await svc.get_all_latest(exchange)
    return {
        "exchange": exchange,
        "count": len(entries),
        "entries": [_entry_to_dict(e, compact=compact) for e in entries],
    }


@router.post("/generate-all")
async def generate_all_dossiers(
    exchange: str = Query("bitfinex", description="Exchange code"),
    delay: float = Query(10.0, ge=0, le=120, description="Seconds between each generation (spreads hw load)"),
):
    """Queue today's dossier generation for all coins.

    Returns immediately — generation runs in the background with
    configurable delay between each coin to spread hardware load.
    Check progress via GET /dossier/queue/status.
    """
    queue = get_queue(delay_seconds=delay)
    status = await queue.enqueue_all(exchange)
    return {
        "status": "queued" if status.state.value == "running" else status.state.value,
        "exchange": exchange,
        "total": status.total,
        "delay_seconds": delay,
        "message": f"Generating {status.total} dossiers with {delay}s delay between each. "
        f"Check GET /dossier/queue/status for progress.",
    }


@router.get("/queue/status")
async def get_queue_status():
    """Get current dossier generation queue status and progress."""
    queue = get_queue()
    return queue.status.to_dict()


@router.post("/queue/cancel")
async def cancel_queue():
    """Cancel the currently running dossier generation queue."""
    queue = get_queue()
    cancelled = queue.cancel()
    return {
        "cancelled": cancelled,
        "status": queue.status.to_dict(),
    }


# =======================================================================
# PARAMETERIZED ROUTES (/{symbol} — must come AFTER static routes)
# =======================================================================


@router.get("/{symbol}")
async def get_coin_dossier(
    symbol: str,
    exchange: str = Query("bitfinex", description="Exchange code"),
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
):
    """Get dossier history for a specific coin."""
    svc = _get_service()
    entries = await svc.get_history(exchange, symbol.upper(), days)
    if not entries:
        raise HTTPException(
            status_code=404,
            detail=f"No dossier entries found for {exchange}:{symbol}",
        )
    return {
        "exchange": exchange,
        "symbol": symbol.upper(),
        "count": len(entries),
        "entries": [_entry_to_dict(e) for e in entries],
    }


@router.get("/{symbol}/{entry_date}")
async def get_coin_dossier_entry(
    symbol: str,
    entry_date: date,
    exchange: str = Query("bitfinex", description="Exchange code"),
):
    """Get a specific dossier entry by date."""
    svc = _get_service()
    entry = await svc.get_entry(exchange, symbol.upper(), entry_date)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"No dossier entry for {exchange}:{symbol} on {entry_date}",
        )
    return _entry_to_dict(entry)


@router.post("/{symbol}/generate")
async def generate_coin_dossier(
    symbol: str,
    exchange: str = Query("bitfinex", description="Exchange code"),
):
    """Generate (or regenerate) today's dossier entry for a coin."""
    svc = _get_service()
    try:
        entry = await svc.generate_entry(exchange, symbol.upper())
        return {
            "status": "generated",
            "entry": _entry_to_dict(entry),
        }
    except Exception as e:
        logger.exception(f"Failed to generate dossier for {symbol}")
        raise HTTPException(
            status_code=500,
            detail=f"Dossier generation failed: {e}",
        ) from e


# -----------------------------------------------------------------------
# Serialization helper
# -----------------------------------------------------------------------


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return 0.0


def _entry_to_dict(entry, *, compact: bool = False) -> dict:
    """Convert a DossierEntry to a JSON-serializable dict."""
    base = {
        "id": entry.id,
        "exchange": entry.exchange,
        "symbol": entry.symbol,
        "entry_date": str(entry.entry_date),
        "price": _as_float(entry.price),
        "change_24h": _as_float(entry.change_24h),
        "change_7d": _as_float(entry.change_7d),
        "volume_24h": _as_float(entry.volume_24h),
        "rsi": _as_float(entry.rsi),
        "macd_signal": entry.macd_signal,
        "ema_trend": entry.ema_trend,
        "support_level": _as_float(entry.support_level),
        "resistance_level": _as_float(entry.resistance_level),
        "signal_score": _as_float(entry.signal_score),
        "predicted_direction": entry.predicted_direction,
        "predicted_target": _as_float(entry.predicted_target),
        "predicted_timeframe": entry.predicted_timeframe,
        "prediction_correct": entry.prediction_correct,
    }

    if compact:
        return {
            **base,
            "stats_summary": entry.stats_summary,
        }

    return {
        **base,
        "lore": entry.lore,
        "stats_summary": entry.stats_summary,
        "tech_analysis": entry.tech_analysis,
        "retrospective": entry.retrospective,
        "prediction": entry.prediction,
        "full_narrative": entry.full_narrative,
        "model_used": entry.model_used,
        "tokens_used": entry.tokens_used,
        "generation_time_ms": entry.generation_time_ms,
        "created_at": str(entry.created_at) if entry.created_at else None,
    }
