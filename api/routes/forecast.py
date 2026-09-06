"""TimesFM forecasting API routes (2.5 / 3.0 backends).

Endpoints:
- ``POST /forecast``        — probabilistic forecast for one symbol.
- ``POST /forecast/batch``  — forecast many symbols with one batched model call.
- ``GET  /forecast/status`` — model load status (triggers the lazy load).

Data source: the most recent closed candles from the same ``candles`` table the
``/candles`` endpoints use (symbols without slash, e.g. ``BTCUSD``).

Route ordering: static/literal paths are declared first (this router has no
parameterized ``/{...}`` routes, the ordering is kept defensive anyway).

Concurrency: model load and inference run through a module-level
ThreadPoolExecutor so torch never blocks the FastAPI event loop. The executor
is dedicated to forecasting instead of the shared app executor on purpose: a
long CPU inference must not starve other background tasks.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.forecasting.cache import get_forecast_cache
from core.forecasting.models import ForecastPoint, ForecastResult
from core.forecasting.service import MIN_CONTEXT_POINTS, TimesFMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecast", tags=["forecast"])

# Singleton service (lazy init) + dedicated inference executor.
_service: TimesFMService | None = None
_service_lock = threading.Lock()
_INFERENCE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="timesfm")

_TIMEFRAME_RE = re.compile(r"^(\d+)([mhdw])$")
_TIMEFRAME_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def _get_service() -> TimesFMService:
    """Get or lazily create the TimesFM service singleton."""
    global _service
    with _service_lock:
        if _service is None:
            _service = TimesFMService()
        return _service


def set_service(service: TimesFMService | None) -> None:
    """Replace the service singleton (test seam; ``None`` re-enables lazy init)."""
    global _service
    _service = service


# =======================================================================
# Request/response models
# =======================================================================


class ForecastRequest(BaseModel):
    """Request body for ``POST /forecast``."""

    symbol: str = Field(..., min_length=1, description="Trading symbol without slash (e.g. BTCUSD)")
    timeframe: str = Field("1h", min_length=1, description="Candle timeframe (e.g. 1m, 5m, 1h)")
    horizon: int = Field(24, ge=1, description="Number of steps to forecast")
    exchange: str = Field("bitfinex", min_length=1, description="Exchange name")


class BatchForecastRequest(BaseModel):
    """Request body for ``POST /forecast/batch``."""

    symbols: list[str] = Field(..., min_length=1, description="Symbols without slash (e.g. BTCUSD)")
    timeframe: str = Field("1h", min_length=1, description="Candle timeframe (e.g. 1m, 5m, 1h)")
    horizon: int = Field(24, ge=1, description="Number of steps to forecast")
    exchange: str = Field("bitfinex", min_length=1, description="Exchange name")


# =======================================================================
# Helpers
# =======================================================================


def _timeframe_to_timedelta(timeframe: str) -> timedelta:
    """Convert a candle timeframe (``1m``, ``5m``, ``1h``, ``4h``, ``1d``...) to a timedelta.

    Raises:
        HTTPException: 422 when the timeframe cannot be parsed.
    """
    match = _TIMEFRAME_RE.match(timeframe.strip().lower())
    if not match:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_timeframe",
                "message": f"Cannot parse timeframe {timeframe!r} (expected e.g. 1m, 5m, 1h, 4h, 1d)",
            },
        )
    amount, unit = int(match.group(1)), match.group(2)
    if amount <= 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unsupported_timeframe",
                "message": f"Timeframe amount must be positive, got {timeframe!r}",
            },
        )
    return timedelta(seconds=amount * _TIMEFRAME_UNIT_SECONDS[unit])


def _validate_horizon(service: TimesFMService, horizon: int) -> None:
    """Validate the horizon against the configured maximum (422 when out of range)."""
    max_horizon = service.config.max_horizon
    if not 1 <= int(horizon) <= max_horizon:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "horizon_out_of_range",
                "message": f"horizon must be between 1 and {max_horizon}, got {horizon}",
            },
        )


def _fetch_closes(
    exchange: str,
    symbol: str,
    timeframe: str,
    limit: int,
) -> tuple[list[int], np.ndarray]:
    """Fetch the most recent closed candles for a symbol.

    Uses the same ``candles`` table/store access pattern as ``GET /candles``
    in ``api/main.py``. The ``api.main`` import is deferred into this function
    because ``api.main`` imports this module at startup (circular import).

    Args:
        exchange: Exchange name (e.g. ``bitfinex``).
        symbol: Trading symbol without slash (e.g. ``BTCUSD``).
        timeframe: Candle timeframe (e.g. ``1h``).
        limit: Maximum number of candles to fetch.

    Returns:
        Tuple ``(open_times_ms, closes)`` in ascending time order, where
        ``open_times_ms`` are epoch milliseconds of the candle open times and
        ``closes`` is a ``np.float32`` array of close prices.

    Raises:
        HTTPException: 404 when no candles exist for the series.
    """
    from api.main import _get_stores  # noqa: PLC0415  (deferred: avoids circular import)

    stores = _get_stores()
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    stmt = text(
        """
        SELECT open_time, close
        FROM candles
        WHERE exchange = :exchange
          AND symbol = :symbol
          AND timeframe = :timeframe
        ORDER BY open_time DESC
        LIMIT :limit
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(
            stmt,
            {"exchange": exchange, "symbol": symbol, "timeframe": timeframe, "limit": limit},
        ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_data",
                "message": f"No candles found for {exchange}:{symbol}:{timeframe}",
            },
        )

    rows = list(reversed(rows))  # ascending time order for the model context
    open_times_ms: list[int] = []
    closes: list[float] = []
    for open_time, close in rows:
        dt = open_time if open_time.tzinfo else open_time.replace(tzinfo=timezone.utc)
        open_times_ms.append(int(dt.timestamp() * 1000))
        closes.append(float(close))
    return open_times_ms, np.asarray(closes, dtype=np.float32)


def _build_points(
    last_closed_candle_ts: int,
    step: timedelta,
    bands: list[tuple[float, float, float]],
) -> list[ForecastPoint]:
    """Attach future timestamps to forecast bands.

    Args:
        last_closed_candle_ts: Epoch milliseconds of the last closed candle's
            open time.
        step: Candle timeframe as a timedelta.
        bands: One ``(p10, p50, p90)`` tuple per horizon step.

    Returns:
        Forecast points with ISO-8601 UTC timestamps (the candles following
        the last closed one).
    """
    base = datetime.fromtimestamp(last_closed_candle_ts / 1000.0, tz=timezone.utc)
    return [
        ForecastPoint(
            ts=(base + step * (index + 1)).isoformat(),
            p10=band[0],
            p50=band[1],
            p90=band[2],
        )
        for index, band in enumerate(bands)
    ]


def _service_metadata(service: TimesFMService) -> dict[str, Any]:
    """Operational metadata recorded in every forecast result."""
    return {"device": service.device, "model_id": service.config.model_id}


# =======================================================================
# Sync workers (executed on the inference executor, never on the event loop)
# =======================================================================


def _forecast_symbol_sync(exchange: str, symbol: str, timeframe: str, horizon: int) -> dict[str, Any]:
    """Forecast one symbol (DB fetch, cache check, model call) — sync context."""
    started = time.perf_counter()
    service = _get_service()
    service.load()

    open_times_ms, closes = _fetch_closes(
        exchange, symbol, timeframe, limit=service.config.max_context
    )
    last_closed_ts = open_times_ms[-1]

    cache = get_forecast_cache()
    cached = cache.get(symbol, timeframe, horizon, last_closed_ts)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if cached is not None:
        return cached.to_api_dict(cache="hit", latency_ms=elapsed_ms)

    if closes.size < MIN_CONTEXT_POINTS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "insufficient_data",
                "message": (
                    f"Forecast requires at least {MIN_CONTEXT_POINTS} closed candles, "
                    f"got {closes.size} for {exchange}:{symbol}:{timeframe}"
                ),
                "available": int(closes.size),
                "required": MIN_CONTEXT_POINTS,
            },
        )

    step = _timeframe_to_timedelta(timeframe)
    bands = service.forecast([closes], horizon)[0]
    result = ForecastResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        horizon=horizon,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_id=service.config.model_id,
        context_len=int(closes.size),
        points=_build_points(last_closed_ts, step, bands),
        meta={**_service_metadata(service), "cache": "miss"},
    )
    cache.set(symbol, timeframe, horizon, last_closed_ts, result)
    return result.to_api_dict(
        cache="miss", latency_ms=(time.perf_counter() - started) * 1000.0
    )


def _forecast_batch_sync(
    exchange: str, symbols: list[str], timeframe: str, horizon: int
) -> dict[str, Any]:
    """Forecast many symbols; all cache misses share ONE ``service.forecast`` call."""
    started = time.perf_counter()
    service = _get_service()
    service.load()
    cache = get_forecast_cache()

    unique_symbols = list(dict.fromkeys(s.upper() for s in symbols))
    errors: dict[str, Any] = {}
    fetched: dict[str, tuple[int, np.ndarray]] = {}

    for symbol in unique_symbols:
        try:
            open_times_ms, closes = _fetch_closes(
                exchange, symbol, timeframe, limit=service.config.max_context
            )
        except HTTPException as exc:
            errors[symbol] = exc.detail
            continue
        if closes.size < MIN_CONTEXT_POINTS:
            errors[symbol] = {
                "error": "insufficient_data",
                "message": (
                    f"Forecast requires at least {MIN_CONTEXT_POINTS} closed candles, "
                    f"got {closes.size} for {exchange}:{symbol}:{timeframe}"
                ),
                "available": int(closes.size),
                "required": MIN_CONTEXT_POINTS,
            }
            continue
        fetched[symbol] = (open_times_ms[-1], closes)

    results: dict[str, Any] = {}
    pending_symbols: list[str] = []
    pending_series: list[np.ndarray] = []
    pending_last_ts: list[int] = []

    for symbol, (last_closed_ts, closes) in fetched.items():
        cached = cache.get(symbol, timeframe, horizon, last_closed_ts)
        if cached is not None:
            results[symbol] = cached.to_api_dict(
                cache="hit", latency_ms=(time.perf_counter() - started) * 1000.0
            )
        else:
            pending_symbols.append(symbol)
            pending_series.append(closes)
            pending_last_ts.append(last_closed_ts)

    if pending_series:
        step = _timeframe_to_timedelta(timeframe)
        bands_batch = service.forecast(pending_series, horizon)  # single batched call
        generated_at = datetime.now(timezone.utc).isoformat()
        for symbol, last_closed_ts, closes, bands in zip(
            pending_symbols, pending_last_ts, pending_series, bands_batch, strict=True
        ):
            result = ForecastResult(
                symbol=symbol,
                timeframe=timeframe,
                horizon=horizon,
                generated_at=generated_at,
                model_id=service.config.model_id,
                context_len=int(closes.size),
                points=_build_points(last_closed_ts, step, bands),
                meta={**_service_metadata(service), "cache": "miss"},
            )
            cache.set(symbol, timeframe, horizon, last_closed_ts, result)
            results[symbol] = result.to_api_dict(
                cache="miss", latency_ms=(time.perf_counter() - started) * 1000.0
            )

    return {
        "timeframe": timeframe,
        "horizon": horizon,
        "model_id": service.config.model_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "errors": errors,
    }


# =======================================================================
# Routes (static paths first — no parameterized routes in this router)
# =======================================================================


@router.get("/status")
async def forecast_status() -> dict[str, Any]:
    """Model load status; the first call triggers the lazy model load."""
    service = _get_service()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_INFERENCE_EXECUTOR, service.load)
    return service.status()


@router.post("/batch")
async def forecast_batch(request: BatchForecastRequest) -> dict[str, Any]:
    """Forecast several symbols with a single batched model call.

    Symbols served from cache or failing data requirements are split out:
    ``results`` holds per-symbol payloads, ``errors`` per-symbol error details.
    """
    service = _get_service()
    _validate_horizon(service, request.horizon)
    _timeframe_to_timedelta(request.timeframe)  # fail fast on unparsable timeframes

    loop = asyncio.get_running_loop()
    worker = partial(
        _forecast_batch_sync,
        request.exchange,
        request.symbols,
        request.timeframe,
        request.horizon,
    )
    return await loop.run_in_executor(_INFERENCE_EXECUTOR, worker)


@router.post("")
async def forecast(request: ForecastRequest) -> dict[str, Any]:
    """Forecast the next ``horizon`` closes for one symbol.

    Returns per-step p10/p50/p90 quantiles from the TimesFM quantile head
    (backend per TIMESFM_BACKEND / model id); repeated calls within the same
    candle are served from the TTL cache.
    """
    service = _get_service()
    _validate_horizon(service, request.horizon)
    _timeframe_to_timedelta(request.timeframe)  # fail fast on unparsable timeframes

    loop = asyncio.get_running_loop()
    worker = partial(
        _forecast_symbol_sync,
        request.exchange,
        request.symbol,
        request.timeframe,
        request.horizon,
    )
    return await loop.run_in_executor(_INFERENCE_EXECUTOR, worker)
