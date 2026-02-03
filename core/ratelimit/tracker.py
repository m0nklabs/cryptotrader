"""Rate limit tracking for exchange API calls.

Tracks API request counts, quotas, and reset times per exchange and endpoint.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass
class RateLimitInfo:
    """Rate limit information for a specific endpoint."""

    exchange: str
    endpoint: str
    limit: int  # Total requests allowed
    remaining: int  # Requests remaining
    reset_at: float  # Unix timestamp when limit resets
    window_seconds: int = 60  # Default 60 second window

    @property
    def used(self) -> int:
        """Number of requests used."""
        return self.limit - self.remaining

    @property
    def usage_percent(self) -> float:
        """Usage percentage (0-100)."""
        if self.limit == 0:
            return 0.0
        return (self.used / self.limit) * 100

    @property
    def reset_in_seconds(self) -> int:
        """Seconds until rate limit resets."""
        remaining = int(self.reset_at - time.time())
        return max(0, remaining)

    @property
    def status(self) -> str:
        """Status indicator: ok, warning, critical."""
        usage = self.usage_percent
        if usage >= 90:
            return "critical"
        elif usage >= 70:
            return "warning"
        return "ok"


@dataclass
class RateLimitTracker:
    """Thread-safe rate limit tracker."""

    _limits: dict[str, RateLimitInfo] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def _make_key(self, exchange: str, endpoint: str) -> str:
        """Create cache key for exchange + endpoint."""
        return f"{exchange}:{endpoint}"

    def update(
        self,
        exchange: str,
        endpoint: str,
        limit: int,
        remaining: int,
        reset_at: float,
        window_seconds: int = 60,
    ) -> None:
        """Update rate limit information."""
        key = self._make_key(exchange, endpoint)
        with self._lock:
            self._limits[key] = RateLimitInfo(
                exchange=exchange,
                endpoint=endpoint,
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                window_seconds=window_seconds,
            )

    def get(self, exchange: str, endpoint: str) -> Optional[RateLimitInfo]:
        """Get rate limit info for a specific endpoint."""
        key = self._make_key(exchange, endpoint)
        with self._lock:
            return self._limits.get(key)

    def get_all(self, exchange: Optional[str] = None) -> list[RateLimitInfo]:
        """Get all rate limit info, optionally filtered by exchange."""
        with self._lock:
            limits = list(self._limits.values())

        if exchange:
            limits = [l for l in limits if l.exchange == exchange]

        return sorted(limits, key=lambda x: (x.exchange, x.endpoint))

    def increment_usage(self, exchange: str, endpoint: str) -> None:
        """Increment usage count for an endpoint (manual tracking)."""
        key = self._make_key(exchange, endpoint)
        with self._lock:
            if key in self._limits:
                info = self._limits[key]
                if info.remaining > 0:
                    # Decrement remaining count
                    self._limits[key] = RateLimitInfo(
                        exchange=info.exchange,
                        endpoint=info.endpoint,
                        limit=info.limit,
                        remaining=info.remaining - 1,
                        reset_at=info.reset_at,
                        window_seconds=info.window_seconds,
                    )

    def should_throttle(self, exchange: str, endpoint: str, threshold: float = 0.9) -> bool:
        """Check if requests should be throttled based on usage threshold."""
        info = self.get(exchange, endpoint)
        if not info:
            return False

        # Check if we've exceeded threshold
        return info.usage_percent >= (threshold * 100)

    def clear_expired(self) -> None:
        """Remove expired rate limit entries."""
        now = time.time()
        with self._lock:
            expired_keys = [key for key, info in self._limits.items() if info.reset_at < now]
            for key in expired_keys:
                del self._limits[key]


# Global tracker instance
_tracker = RateLimitTracker()


def get_tracker() -> RateLimitTracker:
    """Get the global rate limit tracker instance."""
    return _tracker
