"""FastAPI middleware for rate limit tracking."""

from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.ratelimit.tracker import get_tracker


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to track and parse rate limit headers from exchange APIs.

    NOTE: This middleware currently tracks rate limit headers from OUR API responses.
    For tracking EXCHANGE rate limits, consider updating exchange client code to call
    tracker.update() after each outbound exchange API request instead.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and extract rate limit headers from response."""
        # Call next middleware/endpoint
        response = await call_next(request)

        # Extract rate limit headers if present
        # Common header patterns:
        # - X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
        # - RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset

        limit_header = response.headers.get("x-ratelimit-limit") or response.headers.get("ratelimit-limit")
        remaining_header = response.headers.get("x-ratelimit-remaining") or response.headers.get("ratelimit-remaining")
        reset_header = response.headers.get("x-ratelimit-reset") or response.headers.get("ratelimit-reset")

        if limit_header and remaining_header and reset_header:
            try:
                # Parse rate limit info
                limit = int(limit_header)
                remaining = int(remaining_header)
                reset_at = float(reset_header)

                # Determine exchange from request path or headers
                # Format: /api/{exchange}/{endpoint}
                path_parts = request.url.path.split("/")
                exchange = path_parts[2] if len(path_parts) > 2 else "unknown"
                endpoint = path_parts[3] if len(path_parts) > 3 else "unknown"

                # Update tracker
                tracker = get_tracker()
                tracker.update(
                    exchange=exchange,
                    endpoint=endpoint,
                    limit=limit,
                    remaining=remaining,
                    reset_at=reset_at,
                )
            except (ValueError, IndexError):
                # Invalid headers, skip
                pass

        return response
