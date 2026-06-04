"""Tests for signal scoring module."""

from __future__ import annotations

import pytest

from core.signals.scoring import (
    IndicatorContribution,
    ScoringResult,
    normalize_weights,
    score_signals,
)
from core.types import IndicatorSignal


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


def test_score_signals_basic():
    """Test basic signal scoring with deterministic inputs."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=80, value="RSI=25", reason="Oversold"),
        IndicatorSignal(code="MACD", side="BUY", strength=60, value="MACD>0", reason="Bullish crossover"),
    ]
    weights = {"RSI": 0.4, "MACD": 0.6}

    result = score_signals(signals=signals, weights=weights)

    # Score = 0.4 * 80 + 0.6 * 60 = 32 + 36 = 68
    assert result.score == 68
    assert len(result.contributions) == 2
    assert isinstance(result.explanation, str)
    assert "68/100" in result.explanation


def test_score_signals_auto_normalize():
    """Test that weights are auto-normalized."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=80, value="RSI=25", reason="Oversold"),
        IndicatorSignal(code="MACD", side="BUY", strength=60, value="MACD>0", reason="Bullish crossover"),
    ]
    # Non-normalized weights (sum to 10 instead of 1)
    weights = {"RSI": 4.0, "MACD": 6.0}

    result = score_signals(signals=signals, weights=weights)

    # After normalization: RSI=0.4, MACD=0.6
    # Score = 0.4 * 80 + 0.6 * 60 = 68
    assert result.score == 68


def test_score_signals_contributions():
    """Test that per-indicator contributions are calculated correctly."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=50, value="RSI=30", reason="Oversold"),
        IndicatorSignal(code="MACD", side="BUY", strength=70, value="MACD>0", reason="Bullish"),
    ]
    weights = {"RSI": 0.5, "MACD": 0.5}

    result = score_signals(signals=signals, weights=weights)

    # Find contributions
    rsi_contrib = next(c for c in result.contributions if c.code == "RSI")
    macd_contrib = next(c for c in result.contributions if c.code == "MACD")

    assert rsi_contrib.strength == 50
    assert rsi_contrib.weight == pytest.approx(0.5)
    assert rsi_contrib.contribution == pytest.approx(25.0)

    assert macd_contrib.strength == 70
    assert macd_contrib.weight == pytest.approx(0.5)
    assert macd_contrib.contribution == pytest.approx(35.0)


def test_score_signals_explanation():
    """Test that explanation is human-readable and contains key information."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=80, value="RSI=25", reason="Oversold"),
    ]
    weights = {"RSI": 1.0}

    result = score_signals(signals=signals, weights=weights)

    # Check explanation contains score and indicator details
    assert "80/100" in result.explanation
    assert "RSI" in result.explanation
    assert "80.0 pts" in result.explanation or "80 pts" in result.explanation


def test_score_signals_empty():
    """Test scoring with empty signals list."""
    signals = []
    weights = {"RSI": 1.0}

    result = score_signals(signals=signals, weights=weights)

    assert result.score == 0
    assert len(result.contributions) == 0
    assert "No signals" in result.explanation


def test_score_signals_zero_weights():
    """Test that zero weights raise ValueError."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=80, value="RSI=25", reason="Oversold"),
    ]
    weights = {"RSI": 0.0}

    with pytest.raises(ValueError, match="weights total must be > 0"):
        score_signals(signals=signals, weights=weights)


def test_score_signals_missing_weight():
    """Test signal with no matching weight contributes 0."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=80, value="RSI=25", reason="Oversold"),
        IndicatorSignal(code="UNKNOWN", side="BUY", strength=100, value="?", reason="Unknown indicator"),
    ]
    weights = {"RSI": 1.0}  # No weight for UNKNOWN

    result = score_signals(signals=signals, weights=weights)

    # Only RSI contributes
    assert result.score == 80
    assert len(result.contributions) == 2

    # UNKNOWN should have 0 weight and 0 contribution
    unknown_contrib = next(c for c in result.contributions if c.code == "UNKNOWN")
    assert unknown_contrib.weight == 0.0
    assert unknown_contrib.contribution == 0.0


def test_score_signals_clamping():
    """Test that signal strengths are clamped to 0-100 range."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=150, value="RSI=0", reason="Way oversold"),  # Over 100
        IndicatorSignal(code="MACD", side="BUY", strength=-20, value="MACD<0", reason="Negative"),  # Below 0
    ]
    weights = {"RSI": 0.5, "MACD": 0.5}

    result = score_signals(signals=signals, weights=weights)

    # RSI clamped to 100, MACD clamped to 0
    # Score = 0.5 * 100 + 0.5 * 0 = 50
    assert result.score == 50

    rsi_contrib = next(c for c in result.contributions if c.code == "RSI")
    macd_contrib = next(c for c in result.contributions if c.code == "MACD")

    assert rsi_contrib.strength == 100  # Clamped
    assert macd_contrib.strength == 0  # Clamped


def test_score_signals_multiple_indicators():
    """Test scoring with variable number of indicators."""
    # Test with 3 indicators
    signals_3 = [
        IndicatorSignal(code="RSI", side="BUY", strength=60, value="RSI=30", reason="Oversold"),
        IndicatorSignal(code="MACD", side="BUY", strength=70, value="MACD>0", reason="Bullish"),
        IndicatorSignal(code="STOCH", side="BUY", strength=50, value="STOCH=20", reason="Oversold"),
    ]
    weights_3 = {"RSI": 0.3, "MACD": 0.4, "STOCH": 0.3}

    result_3 = score_signals(signals=signals_3, weights=weights_3)
    # Score = 0.3*60 + 0.4*70 + 0.3*50 = 18 + 28 + 15 = 61
    assert result_3.score == 61
    assert len(result_3.contributions) == 3

    # Test with 5 indicators
    signals_5 = signals_3 + [
        IndicatorSignal(code="BB", side="BUY", strength=80, value="BB", reason="Lower band"),
        IndicatorSignal(code="VOL", side="CONFIRM", strength=90, value="VOL", reason="High volume"),
    ]
    weights_5 = {"RSI": 0.2, "MACD": 0.2, "STOCH": 0.2, "BB": 0.2, "VOL": 0.2}

    result_5 = score_signals(signals=signals_5, weights=weights_5)
    # Score = 0.2*60 + 0.2*70 + 0.2*50 + 0.2*80 + 0.2*90 = 12+14+10+16+18 = 70
    assert result_5.score == 70
    assert len(result_5.contributions) == 5


def test_score_signals_uniform_weights():
    """Test scoring with uniform weights across indicators."""
    signals = [
        IndicatorSignal(code="A", side="BUY", strength=20, value="A", reason="A"),
        IndicatorSignal(code="B", side="BUY", strength=40, value="B", reason="B"),
        IndicatorSignal(code="C", side="BUY", strength=60, value="C", reason="C"),
        IndicatorSignal(code="D", side="BUY", strength=80, value="D", reason="D"),
    ]
    # All weights equal
    weights = {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0}

    result = score_signals(signals=signals, weights=weights)

    # Average: (20 + 40 + 60 + 80) / 4 = 50
    assert result.score == 50


def test_score_signals_weighted_average():
    """Test that score is properly weighted average, not simple average."""
    signals = [
        IndicatorSignal(code="HIGH_WEIGHT", side="BUY", strength=100, value="HW", reason="High"),
        IndicatorSignal(code="LOW_WEIGHT", side="BUY", strength=0, value="LW", reason="Low"),
    ]
    weights = {"HIGH_WEIGHT": 0.9, "LOW_WEIGHT": 0.1}

    result = score_signals(signals=signals, weights=weights)

    # Score = 0.9 * 100 + 0.1 * 0 = 90
    assert result.score == 90

    # Simple average would be 50, proving this is weighted
    assert result.score != 50


def test_score_signals_result_type():
    """Test that result is ScoringResult with correct types."""
    signals = [
        IndicatorSignal(code="RSI", side="BUY", strength=75, value="RSI=28", reason="Oversold"),
    ]
    weights = {"RSI": 1.0}

    result = score_signals(signals=signals, weights=weights)

    assert isinstance(result, ScoringResult)
    assert isinstance(result.score, int)
    assert isinstance(result.contributions, tuple)
    assert isinstance(result.explanation, str)

    # Check contribution type
    assert len(result.contributions) == 1
    assert isinstance(result.contributions[0], IndicatorContribution)
