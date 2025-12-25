"""Tests for configurable indicator weights."""

from __future__ import annotations

import pytest

from core.signals.scoring import normalize_weights
from core.signals.weights import (
    DEFAULT_WEIGHTS,
    get_weights,
    get_weights_async,
    load_weights_from_db,
)


def test_default_weights_exist():
    """Test that default weights are defined."""
    assert DEFAULT_WEIGHTS is not None
    assert len(DEFAULT_WEIGHTS) > 0
    assert "RSI" in DEFAULT_WEIGHTS
    assert "MACD" in DEFAULT_WEIGHTS


def test_default_weights_valid():
    """Test that default weights are positive and reasonable."""
    for code, weight in DEFAULT_WEIGHTS.items():
        assert weight > 0, f"{code} weight must be positive"
        assert weight <= 1.0, f"{code} weight must be <= 1.0"


def test_default_weights_sum_to_one():
    """Test that default weights sum to 1.0 (or close to it)."""
    total = sum(DEFAULT_WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=0.01)


def test_normalize_weights_basic():
    """Test basic weight normalization."""
    weights = {"RSI": 2.0, "MACD": 3.0}
    normalized = normalize_weights(weights)

    assert normalized["RSI"] == pytest.approx(0.4)  # 2/5
    assert normalized["MACD"] == pytest.approx(0.6)  # 3/5
    assert sum(normalized.values()) == pytest.approx(1.0)


def test_normalize_weights_already_normalized():
    """Test that already normalized weights stay normalized."""
    weights = {"RSI": 0.3, "MACD": 0.7}
    normalized = normalize_weights(weights)

    assert normalized["RSI"] == pytest.approx(0.3)
    assert normalized["MACD"] == pytest.approx(0.7)
    assert sum(normalized.values()) == pytest.approx(1.0)


def test_normalize_weights_single():
    """Test normalization with a single weight."""
    weights = {"RSI": 5.0}
    normalized = normalize_weights(weights)

    assert normalized["RSI"] == pytest.approx(1.0)


def test_normalize_weights_zero_total():
    """Test that zero total weight raises ValueError."""
    weights = {"RSI": 0.0, "MACD": 0.0}

    with pytest.raises(ValueError, match="weights total must be > 0"):
        normalize_weights(weights)


def test_normalize_weights_negative_total():
    """Test that negative total weight raises ValueError."""
    weights = {"RSI": -1.0, "MACD": -2.0}

    with pytest.raises(ValueError, match="weights total must be > 0"):
        normalize_weights(weights)


def test_normalize_weights_with_defaults():
    """Test normalization of default weights (should be idempotent)."""
    # Default weights should already be normalized
    normalized = normalize_weights(DEFAULT_WEIGHTS.copy())

    # Should be very close to original
    for code in DEFAULT_WEIGHTS:
        assert normalized[code] == pytest.approx(DEFAULT_WEIGHTS[code], abs=0.001)


def test_get_weights_no_db():
    """Test get_weights returns defaults when no DB provided."""
    weights = get_weights()

    # Should return normalized defaults
    assert len(weights) == len(DEFAULT_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(1.0)
    for code in DEFAULT_WEIGHTS:
        assert code in weights


def test_get_weights_with_strategy_no_db():
    """Test get_weights returns defaults for custom strategy without DB."""
    weights = get_weights(strategy_id="aggressive")

    # Should still return defaults
    assert len(weights) == len(DEFAULT_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_load_weights_from_db_no_pool():
    """Test load_weights_from_db returns None when no pool provided."""
    result = await load_weights_from_db(strategy_id="default", db_pool=None)
    assert result is None


@pytest.mark.asyncio
async def test_get_weights_async_no_db():
    """Test get_weights_async returns defaults when no DB provided."""
    weights = await get_weights_async(strategy_id="default", db_pool=None)

    # Should return normalized defaults
    assert len(weights) == len(DEFAULT_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(1.0)
    for code in DEFAULT_WEIGHTS:
        assert code in weights


@pytest.mark.asyncio
async def test_load_weights_from_db_with_mock_asyncpg():
    """Test load_weights_from_db with mocked asyncpg pool."""

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        async def fetch(self, query: str, strategy_id: str):
            """Mock fetch method."""
            if strategy_id == "aggressive":
                return [
                    {"indicator_name": "RSI", "weight": 0.30},
                    {"indicator_name": "MACD", "weight": 0.50},
                    {"indicator_name": "STOCHASTIC", "weight": 0.20},
                ]
            return []

    mock_pool = MockAsyncPGPool()
    result = await load_weights_from_db(strategy_id="aggressive", db_pool=mock_pool)

    assert result is not None
    assert result["RSI"] == pytest.approx(0.30)
    assert result["MACD"] == pytest.approx(0.50)
    assert result["STOCHASTIC"] == pytest.approx(0.20)


@pytest.mark.asyncio
async def test_get_weights_async_with_db_override():
    """Test get_weights_async uses DB weights to override defaults."""

    class MockAsyncPGPool:
        """Mock asyncpg connection pool."""

        async def fetch(self, query: str, strategy_id: str):
            """Mock fetch method returning custom weights."""
            return [
                {"indicator_name": "RSI", "weight": 0.50},  # Override default
                {"indicator_name": "MACD", "weight": 0.50},  # Override default
            ]

    mock_pool = MockAsyncPGPool()
    weights = await get_weights_async(strategy_id="custom", db_pool=mock_pool)

    # Should have all indicators (DB overrides + defaults for missing ones)
    assert len(weights) >= 2
    assert sum(weights.values()) == pytest.approx(1.0)

    # DB weights should be present (after normalization with defaults)
    assert "RSI" in weights
    assert "MACD" in weights


@pytest.mark.asyncio
async def test_get_weights_async_db_error_fallback():
    """Test get_weights_async falls back to defaults on DB error."""

    class BrokenPool:
        """Mock pool that raises errors."""

        async def fetch(self, query: str, strategy_id: str):
            """Mock fetch that raises error."""
            raise Exception("DB connection failed")

    broken_pool = BrokenPool()
    weights = await get_weights_async(strategy_id="default", db_pool=broken_pool)

    # Should fallback to defaults
    assert len(weights) == len(DEFAULT_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_normalize_weights_many_indicators():
    """Test normalization with many indicators."""
    weights = {
        "A": 1.0,
        "B": 2.0,
        "C": 3.0,
        "D": 4.0,
        "E": 5.0,
        "F": 6.0,
        "G": 7.0,
    }

    normalized = normalize_weights(weights)

    # Sum should be 1.0
    assert sum(normalized.values()) == pytest.approx(1.0)

    # Each weight should be original / total
    total = sum(weights.values())  # 28
    for code, original_weight in weights.items():
        expected = original_weight / total
        assert normalized[code] == pytest.approx(expected)


def test_normalize_weights_small_values():
    """Test normalization with very small weights."""
    weights = {"RSI": 0.0001, "MACD": 0.0002}

    normalized = normalize_weights(weights)

    assert sum(normalized.values()) == pytest.approx(1.0)
    assert normalized["RSI"] == pytest.approx(1.0 / 3.0)
    assert normalized["MACD"] == pytest.approx(2.0 / 3.0)


def test_normalize_weights_large_values():
    """Test normalization with very large weights."""
    weights = {"RSI": 10000.0, "MACD": 20000.0}

    normalized = normalize_weights(weights)

    assert sum(normalized.values()) == pytest.approx(1.0)
    assert normalized["RSI"] == pytest.approx(1.0 / 3.0)
    assert normalized["MACD"] == pytest.approx(2.0 / 3.0)


@pytest.mark.asyncio
async def test_load_weights_empty_result():
    """Test load_weights_from_db returns None for empty result."""

    class MockEmptyPool:
        """Mock pool that returns empty results."""

        async def fetch(self, query: str, strategy_id: str):
            """Mock fetch returning empty list."""
            return []

    mock_pool = MockEmptyPool()
    result = await load_weights_from_db(strategy_id="nonexistent", db_pool=mock_pool)

    assert result is None


def test_get_weights_returns_copy():
    """Test that get_weights returns a new dict (doesn't share state)."""
    weights1 = get_weights()
    weights2 = get_weights()

    # Modify one
    weights1["RSI"] = 0.99

    # Other should be unchanged
    assert weights2["RSI"] != 0.99
    assert weights2["RSI"] == pytest.approx(DEFAULT_WEIGHTS["RSI"], abs=0.01)


@pytest.mark.asyncio
async def test_get_weights_async_merges_db_with_defaults():
    """Test that DB weights are merged with defaults (not replaced)."""

    class MockPartialPool:
        """Mock pool that returns weights for only some indicators."""

        async def fetch(self, query: str, strategy_id: str):
            """Mock fetch returning partial weights."""
            # Only override RSI, leave others as defaults
            return [
                {"indicator_name": "RSI", "weight": 0.80},
            ]

    mock_pool = MockPartialPool()
    weights = await get_weights_async(strategy_id="partial", db_pool=mock_pool)

    # Should have all default indicators
    for code in DEFAULT_WEIGHTS:
        assert code in weights

    # Sum should still be 1.0 after normalization
    assert sum(weights.values()) == pytest.approx(1.0)
