"""Base LLM provider interface and provider registry."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

import httpx

from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

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
    _lock = asyncio.Lock()

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
    async def get_instance(cls, provider: ProviderName, rate_per_minute: int) -> "TokenBucket":
        """Get or create singleton bucket for provider."""
        async with cls._lock:
            if provider not in cls._instances:
                cls._instances[provider] = cls(rate_per_minute, provider)
            return cls._instances[provider]

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens (wait if necessary).
        
        Args:
            tokens: Number of tokens to acquire (default 1)
        """
        async with self._bucket_lock:
            while True:
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

                # Wait until we have enough tokens
                wait_time = (tokens - self.tokens) / self.rate_per_second
                logger.debug(
                    "Rate limit reached for %s, waiting %.2fs",
                    self.provider.value,
                    wait_time,
                )
                await asyncio.sleep(min(wait_time, 1.0))  # Cap sleep at 1s for responsiveness


# ---------------------------------------------------------------------------
# Error Classification
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(self, message: str, is_transient: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.is_transient = is_transient
        self.status_code = status_code


class TransientError(LLMError):
    """Transient error (retry-able)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message, is_transient=True, status_code=status_code)


class PermanentError(LLMError):
    """Permanent error (not retry-able)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message, is_transient=False, status_code=status_code)


def classify_http_error(status_code: int, message: str) -> LLMError:
    """Classify HTTP errors as transient or permanent.
    
    Args:
        status_code: HTTP status code
        message: Error message
        
    Returns:
        Appropriate LLMError subclass
    """
    # Transient errors (retry-able)
    if status_code in {429, 502, 503, 504}:
        return TransientError(message, status_code)
    
    # Permanent errors (not retry-able)
    if status_code in {400, 401, 403, 404}:
        return PermanentError(message, status_code)
    
    # Default to transient for 5xx (except those explicitly handled)
    if 500 <= status_code < 600:
        return TransientError(message, status_code)
    
    # 4xx errors default to permanent
    if 400 <= status_code < 500:
        return PermanentError(message, status_code)
    
    # Unknown - treat as transient to be safe
    return TransientError(message, status_code)


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
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if jitter:
                        delay *= (0.5 + random.random())  # Add 0-50% jitter
                    
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


# ---------------------------------------------------------------------------
# Response Validation
# ---------------------------------------------------------------------------


def validate_json_response(raw_text: str, required_keys: list[str] | None = None) -> dict[str, Any] | None:
    """Validate and parse JSON response from LLM.
    
    Args:
        raw_text: Raw response text from LLM
        required_keys: Optional list of required keys in the JSON
        
    Returns:
        Parsed JSON dict, or None if invalid
        
    Raises:
        PermanentError: If JSON is malformed and required
    """
    if not raw_text or not raw_text.strip():
        return None
    
    try:
        parsed = json.loads(raw_text)
        
        # Validate required keys if specified
        if required_keys:
            missing = [key for key in required_keys if key not in parsed]
            if missing:
                logger.warning("JSON response missing required keys: %s", missing)
                return None
        
        return parsed
    except json.JSONDecodeError as e:
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

    @property
    def name(self) -> ProviderName:
        return self.config.name

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
        try:
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            # Classify the error
            error = classify_http_error(
                e.response.status_code,
                f"{method} {url} failed: {e.response.text[:200]}",
            )
            raise error
        except httpx.TimeoutException as e:
            # Timeouts are transient
            raise TransientError(f"{method} {url} timed out: {e}")
        except httpx.NetworkError as e:
            # Network errors are transient
            raise TransientError(f"{method} {url} network error: {e}")
        except Exception as e:
            # Unknown errors - permanent
            raise PermanentError(f"{method} {url} failed: {e}")

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
    ) -> AIResponse:
        """Build an error AIResponse without raising."""
        return AIResponse(
            role=request.role,
            provider=self.config.name,
            model=self.config.default_model,
            raw_text="",
            error=error,
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
