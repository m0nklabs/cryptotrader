"""Coin Dossier API routes.

Provides endpoints for coin dossier entries — daily LLM-generated
technical analysis narratives per trading pair.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

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


# -----------------------------------------------------------------------
# GET /dossier/symbols — list coins that have dossier entries
# -----------------------------------------------------------------------


@router.get("/symbols")
async def list_dossier_symbols(
    exchange: str = Query("bitfinex", description="Exchange code"),
):
    """List all symbols that have dossier entries (or available for generation)."""
    svc = _get_service()
    symbols = await svc.get_available_symbols(exchange)
    return {"exchange": exchange, "symbols": symbols}


# -----------------------------------------------------------------------
# GET /dossier/latest — latest dossier entry per coin
# -----------------------------------------------------------------------


@router.get("/latest")
async def get_latest_dossiers(
    exchange: str = Query("bitfinex", description="Exchange code"),
):
    """Get the most recent dossier entry for each coin on the exchange."""
    svc = _get_service()
    entries = await svc.get_all_latest(exchange)
    return {
        "exchange": exchange,
        "count": len(entries),
        "entries": [_entry_to_dict(e) for e in entries],
    }


# -----------------------------------------------------------------------
# GET /dossier/{symbol} — dossier history for a specific coin
# -----------------------------------------------------------------------


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


# -----------------------------------------------------------------------
# GET /dossier/{symbol}/{date} — specific date entry
# -----------------------------------------------------------------------


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


# -----------------------------------------------------------------------
# POST /dossier/{symbol}/generate — trigger generation for one coin
# -----------------------------------------------------------------------


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
# POST /dossier/generate-all — trigger generation for all coins
# -----------------------------------------------------------------------


@router.post("/generate-all")
async def generate_all_dossiers(
    exchange: str = Query("bitfinex", description="Exchange code"),
):
    """Generate today's dossier entries for all coins on the exchange.

    This may take several minutes depending on the number of coins and LLM speed.
    """
    svc = _get_service()
    try:
        entries = await svc.generate_all(exchange)
        return {
            "status": "completed",
            "exchange": exchange,
            "generated": len(entries),
            "entries": [{"symbol": e.symbol, "id": e.id} for e in entries],
        }
    except Exception as e:
        logger.exception("Failed to generate all dossiers")
        raise HTTPException(
            status_code=500,
            detail=f"Bulk dossier generation failed: {e}",
        ) from e


# -----------------------------------------------------------------------
# Serialization helper
# -----------------------------------------------------------------------


def _entry_to_dict(entry) -> dict:
    """Convert a DossierEntry to a JSON-serializable dict."""
    return {
        "id": entry.id,
        "exchange": entry.exchange,
        "symbol": entry.symbol,
        "entry_date": str(entry.entry_date),
        # Stats
        "price": entry.price,
        "change_24h": entry.change_24h,
        "change_7d": entry.change_7d,
        "volume_24h": entry.volume_24h,
        "rsi": entry.rsi,
        "macd_signal": entry.macd_signal,
        "ema_trend": entry.ema_trend,
        "support_level": entry.support_level,
        "resistance_level": entry.resistance_level,
        "signal_score": entry.signal_score,
        # Narrative
        "lore": entry.lore,
        "stats_summary": entry.stats_summary,
        "tech_analysis": entry.tech_analysis,
        "retrospective": entry.retrospective,
        "prediction": entry.prediction,
        "full_narrative": entry.full_narrative,
        # Prediction tracking
        "predicted_direction": entry.predicted_direction,
        "predicted_target": entry.predicted_target,
        "predicted_timeframe": entry.predicted_timeframe,
        "prediction_correct": entry.prediction_correct,
        # Meta
        "model_used": entry.model_used,
        "tokens_used": entry.tokens_used,
        "generation_time_ms": entry.generation_time_ms,
        "created_at": str(entry.created_at) if entry.created_at else None,
    }
