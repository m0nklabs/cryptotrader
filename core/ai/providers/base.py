"""Base LLM provider interface and provider registry."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, NoReturn

import httpx

from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderErrorType, ProviderName

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate Limiting (Token Bucket)
# ---------------------------------------------------------------------------


class TokenBucket:
    """Token bucket rate limiter (singleton per provider).

    Bitfinex-style global singleton pattern — one bucket per provider.
    Allows burst traffic up to the capacity, then refills at a steady rate.
    """

    _instances: dict[ProviderName, "TokenBucket"] = {}
    _lock: asyncio.Lock | None = None

    def __init__(self, rate_per_minute: int, provider: ProviderName) -> None:
        """Initialize token bucket.

        Args:
            rate_per_minute: Requests per minute allowed
            provider: Provider name for this bucket
        """
        self.capacity = rate_per_minute
        self.tokens = float(rate_per_minute)
        self.rate_per_second = rate_per_minute / 60.0
        self.last_update = time.monotonic()
        self.provider = provider
        self._bucket_lock = asyncio.Lock()

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the class-level lock (lazy initialization)."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_instance(cls, provider: ProviderName, rate_per_minute: int) -> "TokenBucket":
        """Get or create singleton bucket for provider."""
        async with cls._get_lock():
            if provider not in cls._instances:
                cls._instances[provider] = cls(rate_per_minute, provider)
            return cls._instances[provider]

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens (wait if necessary).

        Args:
            tokens: Number of tokens to acquire (default 1)
        """
        while True:
            async with self._bucket_lock:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Refill tokens based on elapsed time
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
                self.last_update = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    logger.debug(
                        "Acquired %d token(s) for %s, %.1f remaining",
                        tokens,
                        self.provider.value,
                        self.tokens,
                    )
                    return

                # Calculate wait time but release lock before sleeping
                wait_time = (tokens - self.tokens) / self.rate_per_second
                logger.debug(
                    "Rate limit reached for %s, waiting %.2fs",
                    self.provider.value,
                    wait_time,
                )

            # Sleep outside the lock to allow other coroutines to acquire tokens
            await asyncio.sleep(min(wait_time, 1.0))  # Cap sleep at 1s for responsiveness


# ---------------------------------------------------------------------------
# Error Classification
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(
        self,
        message: str,
        *,
        error_type: ProviderErrorType = ProviderErrorType.UNKNOWN,
        is_transient: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.is_transient = is_transient
        self.status_code = status_code
        self.error_type = error_type


class TransientError(LLMError):
    """Transient error (retry-able)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        error_type: ProviderErrorType = ProviderErrorType.UNKNOWN,
    ):
        super().__init__(
            message,
            error_type=error_type,
            is_transient=True,
            status_code=status_code,
        )


class PermanentError(LLMError):
    """Permanent error (not retry-able)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        error_type: ProviderErrorType = ProviderErrorType.UNKNOWN,
    ):
        super().__init__(
            message,
            error_type=error_type,
            is_transient=False,
            status_code=status_code,
        )


class RateLimitedError(TransientError):
    """HTTP 429 rate limiting."""

    def __init__(self, message: str, status_code: int | None = 429):
        super().__init__(
            message,
            status_code=status_code,
            error_type=ProviderErrorType.RATE_LIMITED,
        )


class ProviderTimeoutError(TransientError):
    """Timeout error (connect/read/write)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(
            message,
            status_code=status_code,
            error_type=ProviderErrorType.TIMEOUT,
        )


class InvalidResponseError(TransientError):
    """Invalid or malformed response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(
            message,
            status_code=status_code,
            error_type=ProviderErrorType.INVALID_RESPONSE,
        )


class AuthError(PermanentError):
    """Authentication/authorization error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(
            message,
            status_code=status_code,
            error_type=ProviderErrorType.AUTH_ERROR,
        )


class NetworkError(TransientError):
    """Network error (DNS, connection reset, etc.)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(
            message,
            status_code=status_code,
            error_type=ProviderErrorType.NETWORK_ERROR,
        )


class ServerError(TransientError):
    """Server-side errors (5xx)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(
            message,
            status_code=status_code,
            error_type=ProviderErrorType.SERVER_ERROR,
        )


class ClientError(PermanentError):
    """Client-side errors (4xx)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(
            message,
            status_code=status_code,
            error_type=ProviderErrorType.CLIENT_ERROR,
        )


def classify_http_error(status_code: int, message: str) -> LLMError:
    """Classify HTTP errors as transient or permanent.

    Args:
        status_code: HTTP status code
        message: Error message

    Returns:
        Appropriate LLMError subclass
    """
    if status_code == 429:
        return RateLimitedError(message, status_code)

    if status_code in {401, 403}:
        return AuthError(message, status_code)

    if status_code == 408:
        return ProviderTimeoutError(message, status_code)

    if 500 <= status_code < 600:
        return ServerError(message, status_code)

    if 400 <= status_code < 500:
        return ClientError(message, status_code)

    # Unexpected status codes (< 400 or >= 600) - treat as permanent
    # since they indicate unexpected behavior that shouldn't be retried
    return PermanentError(message, status_code, error_type=ProviderErrorType.UNKNOWN)


# ---------------------------------------------------------------------------
# Metrics Hook
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderRequestMetrics:
    """Lightweight metrics snapshot for a provider request."""

    provider: ProviderName
    model: str | None
    method: str
    url: str
    status: str
    latency_ms: float
    status_code: int | None = None
    error_type: ProviderErrorType | None = None


# ---------------------------------------------------------------------------
# Retry Logic
# ---------------------------------------------------------------------------


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    jitter: bool = True,
) -> Callable:
    """Decorator for exponential backoff with jitter.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Whether to add random jitter to delays

    Returns:
        Decorated async function with retry logic
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs) -> Any:
            last_error: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except TransientError as e:
                    last_error = e
                    if attempt >= max_retries:
                        logger.error(
                            "Max retries (%d) exceeded for %s: %s",
                            max_retries,
                            func.__name__,
                            e,
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = calculate_backoff_delay(attempt, base_delay, max_delay, jitter=jitter)

                    logger.warning(
                        "Transient error in %s (attempt %d/%d): %s. Retrying in %.2fs",
                        func.__name__,
                        attempt + 1,
                        max_retries + 1,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                except PermanentError as e:
                    logger.error("Permanent error in %s: %s. Not retrying.", func.__name__, e)
                    raise
                except Exception as e:
                    # Unknown errors - treat as permanent for safety
                    logger.error("Unexpected error in %s: %s", func.__name__, e)
                    raise PermanentError(str(e))

            # Should not reach here, but just in case
            raise last_error or Exception("Retry logic error")

        return wrapper

    return decorator


def calculate_backoff_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    *,
    jitter: bool = True,
) -> float:
    """Calculate exponential backoff delay with optional jitter."""
    delay = min(base_delay * (2**attempt), max_delay)
    if jitter:
        delay *= 0.5 + random.random()  # Randomize between 50%-150% of delay
    return delay


# ---------------------------------------------------------------------------
# Response Validation
# ---------------------------------------------------------------------------


def _reject_non_finite_constant(value: str) -> NoReturn:
    raise ValueError(f"Invalid JSON constant: {value}")


def _contains_non_finite_values(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_non_finite_values(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_non_finite_values(item) for item in value)
    return False


def validate_json_response(raw_text: str, required_keys: list[str] | None = None) -> dict[str, Any] | None:
    """Validate and parse JSON response from LLM.

    Args:
        raw_text: Raw response text from LLM
        required_keys: Optional list of required keys in the JSON

    Returns:
        Parsed JSON dict, or None if invalid or missing required keys
    """
    if not raw_text or not raw_text.strip():
        return None

    try:
        parsed = json.loads(raw_text, parse_constant=_reject_non_finite_constant)

        if not isinstance(parsed, dict):
            logger.warning(
                "JSON response is not an object (got %s)",
                type(parsed).__name__,
            )
            return None

        # Validate required keys if specified
        if required_keys:
            missing = [key for key in required_keys if key not in parsed]
            if missing:
                logger.warning("JSON response missing required keys: %s", missing)
                return None

        if _contains_non_finite_values(parsed):
            logger.warning("JSON response contains non-finite values")
            return None

        return parsed
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse JSON response: %s", e)
        return None


class LLMProvider(ABC):
    """Abstract base class for all LLM provider adapters.

    Each provider (DeepSeek, OpenAI, xAI, Ollama, etc.) implements this
    interface.  The router calls ``complete()`` and the adapter handles
    serialisation, auth, rate-limiting, and response parsing.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._rate_limiter: TokenBucket | None = None
        self._metrics_hook: Callable[[ProviderRequestMetrics], None] | None = None

    @property
    def name(self) -> ProviderName:
        return self.config.name

    def set_metrics_hook(self, hook: Callable[[ProviderRequestMetrics], None] | None) -> None:
        """Register a metrics hook for provider request timing/status."""
        self._metrics_hook = hook

    def _record_metrics(self, metrics: ProviderRequestMetrics) -> None:
        if self._metrics_hook is None:
            return
        try:
            self._metrics_hook(metrics)
        except Exception:
            logger.debug("Provider metrics hook failed", exc_info=True)

    def _get_timeout(self) -> httpx.Timeout:
        """Build per-request connect/read/write timeouts."""
        base_timeout = self.config.timeout_seconds
        connect = (
            self.config.timeout_connect_seconds
            if self.config.timeout_connect_seconds is not None
            else base_timeout
        )
        read = (
            self.config.timeout_read_seconds
            if self.config.timeout_read_seconds is not None
            else base_timeout
        )
        write = (
            self.config.timeout_write_seconds
            if self.config.timeout_write_seconds is not None
            else base_timeout
        )
        pool = (
            self.config.timeout_pool_seconds
            if self.config.timeout_pool_seconds is not None
            else base_timeout
        )
        return httpx.Timeout(
            timeout=base_timeout,
            connect=connect,
            read=read,
            write=write,
            pool=pool,
        )

    def _extract_model_name(self, request_kwargs: dict[str, Any]) -> str | None:
        payload = request_kwargs.get("json")
        if isinstance(payload, dict):
            model = payload.get("model")
            if isinstance(model, str):
                return model
        return None

    def _error_type_from_exception(self, exc: Exception) -> ProviderErrorType:
        if isinstance(exc, LLMError):
            return exc.error_type
        return ProviderErrorType.UNKNOWN

    async def _get_rate_limiter(self) -> TokenBucket:
        """Get or create rate limiter for this provider."""
        if self._rate_limiter is None:
            self._rate_limiter = await TokenBucket.get_instance(
                self.config.name,
                self.config.rate_limit_rpm,
            )
        return self._rate_limiter

    @with_retry(max_retries=3, base_delay=1.0, max_delay=10.0, jitter=True)
    async def _make_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make HTTP request with retry and error handling.

        Rate limit tokens are acquired per attempt (including retries) to
        ensure the provider's rate limit is respected even during backoff.

        Args:
            client: HTTP client to use
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional request arguments

        Returns:
            Parsed JSON response

        Raises:
            TransientError: For retry-able errors
            PermanentError: For non-retry-able errors
        """
        # Acquire rate limit token for each attempt (including retries)
        rate_limiter = await self._get_rate_limiter()
        await rate_limiter.acquire()

        start = self._start_timer()
        status_code: int | None = None
        error_type: ProviderErrorType | None = None
        model_name = self._extract_model_name(kwargs)

        try:
            resp = await client.request(method, url, **kwargs)
            status_code = resp.status_code
            resp.raise_for_status()
            try:
                return resp.json()
            except (json.JSONDecodeError, ValueError) as e:
                # Malformed or non-JSON response bodies are typically transient
                # (proxy errors, gateway timeouts with HTML, etc.)
                text_snippet = resp.text[:200] if hasattr(resp, "text") else ""
                raise InvalidResponseError(
                    f"{method} {url} returned invalid JSON: {e}; body snippet: {text_snippet}",
                    status_code=status_code,
                ) from e
        except LLMError as e:
            error_type = e.error_type
            status_code = e.status_code or status_code
            raise
        except httpx.HTTPStatusError as e:
            # Classify the error
            error = classify_http_error(
                e.response.status_code,
                f"{method} {url} failed: {e.response.text[:200]}",
            )
            error_type = error.error_type
            status_code = error.status_code
            raise error from e
        except httpx.TimeoutException as e:
            # Timeouts are transient
            error = ProviderTimeoutError(f"{method} {url} timed out: {e}")
            error_type = error.error_type
            raise error from e
        except httpx.NetworkError as e:
            # Network errors are transient
            error = NetworkError(f"{method} {url} network error: {e}")
            error_type = error.error_type
            raise error from e
        except Exception as e:
            # Unknown errors - permanent
            error = PermanentError(f"{method} {url} failed: {e}", error_type=ProviderErrorType.UNKNOWN)
            error_type = error.error_type
            raise error from e
        finally:
            latency_ms = self._elapsed_ms(start)
            status = "success" if error_type is None else "error"
            self._record_metrics(
                ProviderRequestMetrics(
                    provider=self.config.name,
                    model=model_name,
                    method=method,
                    url=url,
                    status=status,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error_type=error_type,
                )
            )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def complete(
        self,
        request: AIRequest,
        *,
        system_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Send a chat-completion request and return a structured response.

        Args:
            request: The AI request (role, user prompt, context).
            system_prompt: The system prompt to prepend.
            model: Override the provider's default model.
            temperature: Override the default temperature.
            max_tokens: Override the default max tokens.

        Returns:
            An ``AIResponse`` with timing, cost, and parsed content.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the provider is reachable and authenticated."""

    async def complete_stream(
        self,
        request: AIRequest,
        *,
        system_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Stream chat-completion response (optional, provider-specific).

        Args:
            request: The AI request (role, user prompt, context).
            system_prompt: The system prompt to prepend.
            model: Override the provider's default model.
            temperature: Override the default temperature.
            max_tokens: Override the default max tokens.

        Yields:
            Chunks of response text as they arrive.

        Note:
            Default implementation falls back to non-streaming complete().
            Providers that support streaming should override this method.
        """
        # Default: fall back to non-streaming
        response = await self.complete(
            request,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield response.raw_text

    async def close(self) -> None:
        """Close any open HTTP connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _start_timer(self) -> float:
        return time.monotonic()

    def _elapsed_ms(self, start: float) -> float:
        return round((time.monotonic() - start) * 1000, 2)

    def _make_error_response(
        self,
        request: AIRequest,
        error: str,
        latency_ms: float = 0.0,
        error_type: ProviderErrorType | None = None,
        model: str | None = None,
    ) -> AIResponse:
        """Build an error AIResponse without raising."""
        if error_type is None:
            error_type = ProviderErrorType.UNKNOWN
        override_model = getattr(request, "override_model", None)
        effective_model = (
            model
            if model is not None
            else (override_model if override_model is not None else self.config.default_model)
        )
        return AIResponse(
            role=request.role,
            provider=self.config.name,
            model=effective_model,
            raw_text="",
            error=error,
            error_type=error_type,
            latency_ms=latency_ms,
        )


class ProviderRegistry:
    """Singleton registry mapping ``ProviderName`` → ``LLMProvider`` instances.

    Providers register themselves at startup and the router looks them up
    by name at request time.
    """

    _providers: dict[ProviderName, LLMProvider] = {}

    @classmethod
    def register(cls, provider: LLMProvider) -> None:
        """Register a provider instance."""
        cls._providers[provider.name] = provider
        logger.info("Registered LLM provider: %s", provider.name.value)

    @classmethod
    def get(cls, name: ProviderName) -> LLMProvider | None:
        """Get a registered provider by name."""
        return cls._providers.get(name)

    @classmethod
    def all(cls) -> dict[ProviderName, LLMProvider]:
        """Return all registered providers."""
        return dict(cls._providers)

    @classmethod
    async def close_all(cls) -> None:
        """Gracefully close all provider connections."""
        for provider in cls._providers.values():
            await provider.close()
        cls._providers.clear()
