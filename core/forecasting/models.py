"""Data models for the TimesFM forecasting lane.

These are plain dataclasses (no pydantic/torch dependency) so the core
package stays importable in tests and tooling without heavy dependencies.
The API layer converts them to JSON-facing dicts via ``ForecastResult.to_api_dict``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ForecastPoint:
    """One forecast step with the p10/p50/p90 quantile band.

    Attributes:
        ts: ISO-8601 UTC timestamp of the forecasted candle (open time).
        p10: 10th percentile of the predicted close (lower 80% PI bound).
        p50: 50th percentile (median) of the predicted close.
        p90: 90th percentile of the predicted close (upper 80% PI bound).
    """

    ts: str
    p10: float
    p50: float
    p90: float


@dataclass
class ForecastResult:
    """A complete forecast for one symbol/timeframe.

    Attributes:
        symbol: Trading symbol without slash (e.g. ``BTCUSD``).
        timeframe: Candle timeframe (e.g. ``1h``).
        horizon: Number of forecasted steps.
        generated_at: ISO-8601 UTC timestamp when the forecast was computed.
        model_id: Hugging Face model id used for the forecast.
        context_len: Number of context candles the model actually received.
        points: Forecasted points, one per horizon step.
        meta: Operational metadata (device, latency_ms, cache hit/miss, ...).
    """

    symbol: str
    timeframe: str
    horizon: int
    generated_at: str
    model_id: str
    context_len: int
    points: list[ForecastPoint] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_api_dict(
        self,
        *,
        cache: str | None = None,
        latency_ms: float | None = None,
    ) -> dict[str, Any]:
        """Flatten to the JSON response contract of the forecast endpoints.

        Args:
            cache: Override for the cache field (e.g. mark a served-from-cache
                response as ``"hit"``); defaults to ``meta["cache"]``.
            latency_ms: Override for the end-to-end request latency; defaults
                to ``meta["latency_ms"]``.

        Returns:
            Dict with symbol, timeframe, horizon, model_id, generated_at,
            points, cache, latency_ms (plus context_len and device metadata).
        """
        resolved_cache = cache if cache is not None else self.meta.get("cache", "miss")
        resolved_latency = (
            latency_ms if latency_ms is not None else self.meta.get("latency_ms")
        )
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "horizon": self.horizon,
            "model_id": self.model_id,
            "generated_at": self.generated_at,
            "context_len": self.context_len,
            "device": self.meta.get("device"),
            "points": [
                {"ts": p.ts, "p10": p.p10, "p50": p.p50, "p90": p.p90}
                for p in self.points
            ],
            "cache": resolved_cache,
            "latency_ms": resolved_latency,
        }
