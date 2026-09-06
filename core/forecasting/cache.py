"""In-memory TTL cache for forecast results.

Mirrors the ``_market_cap_cache`` pattern from ``api/main.py``: a plain dict
guarded by a ``threading.Lock``. The cache key includes the timestamp of the
last closed candle, so a freshly stored candle automatically invalidates the
previous entry for the same (symbol, timeframe, horizon); the TTL is a
memory-hygiene backstop for symbols that stop receiving new candles.
"""

from __future__ import annotations

import os
import threading
import time

from core.forecasting.models import ForecastResult

DEFAULT_TTL_SECONDS = 1800.0

CacheKey = tuple[str, str, int, int]


class ForecastCache:
    """Small thread-safe TTL cache keyed on forecast inputs + last candle."""

    def __init__(self, ttl_seconds: float | None = None) -> None:
        """Create the cache.

        Args:
            ttl_seconds: Entry lifetime; defaults to ``TIMESFM_CACHE_TTL`` from
                the environment or :data:`DEFAULT_TTL_SECONDS`.
        """
        if ttl_seconds is None:
            try:
                ttl_seconds = float(os.environ.get("TIMESFM_CACHE_TTL", "").strip() or DEFAULT_TTL_SECONDS)
            except ValueError:
                ttl_seconds = DEFAULT_TTL_SECONDS
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._entries: dict[CacheKey, tuple[float, ForecastResult]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def make_key(
        symbol: str,
        timeframe: str,
        horizon: int,
        last_closed_candle_ts: int,
    ) -> CacheKey:
        """Build the cache key.

        Args:
            symbol: Trading symbol without slash (e.g. ``BTCUSD``).
            timeframe: Candle timeframe (e.g. ``1h``).
            horizon: Forecast horizon in steps.
            last_closed_candle_ts: Epoch milliseconds of the last closed
                candle's open time; a new candle changes the key.

        Returns:
            Normalized key tuple.
        """
        return (symbol.upper(), timeframe, int(horizon), int(last_closed_candle_ts))

    def get(
        self,
        symbol: str,
        timeframe: str,
        horizon: int,
        last_closed_candle_ts: int,
    ) -> ForecastResult | None:
        """Look up a cached forecast.

        Args:
            symbol: Trading symbol without slash.
            timeframe: Candle timeframe.
            horizon: Forecast horizon in steps.
            last_closed_candle_ts: Epoch milliseconds of the last closed candle.

        Returns:
            The cached :class:`ForecastResult`, or ``None`` on miss/expiry.
            Expired entries are evicted on read.
        """
        key = self.make_key(symbol, timeframe, horizon, last_closed_candle_ts)
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, result = entry
            if now - stored_at > self._ttl_seconds:
                self._entries.pop(key, None)
                return None
            return result

    def set(
        self,
        symbol: str,
        timeframe: str,
        horizon: int,
        last_closed_candle_ts: int,
        result: ForecastResult,
    ) -> None:
        """Store a forecast result.

        Args:
            symbol: Trading symbol without slash.
            timeframe: Candle timeframe.
            horizon: Forecast horizon in steps.
            last_closed_candle_ts: Epoch milliseconds of the last closed candle.
            result: The result to cache.
        """
        key = self.make_key(symbol, timeframe, horizon, last_closed_candle_ts)
        with self._lock:
            self._entries[key] = (time.time(), result)

    def clear(self) -> None:
        """Drop every cached entry (used by tests and ops)."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        """Number of currently cached entries."""
        with self._lock:
            return len(self._entries)


_cache: ForecastCache | None = None
_cache_lock = threading.Lock()


def get_forecast_cache() -> ForecastCache:
    """Return the process-wide forecast cache singleton (lazy, thread-safe)."""
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = ForecastCache()
        return _cache
