from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.indicators.stochastic import compute_stochastic, generate_stochastic_signal
from core.types import Candle


def _make_candle(close: float, high: float | None = None, low: float | None = None, idx: int = 0) -> Candle:
    """Helper to create a candle with OHLC values."""
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    open_time = base_time + timedelta(hours=idx)
    close_time = base_time + timedelta(hours=idx, minutes=59)

    # Default high/low to close if not provided
    if high is None:
        high = close
    if low is None:
        low = close

    return Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=open_time,
        close_time=close_time,
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


# ========== compute_stochastic tests ==========


def test_compute_stochastic_requires_minimum_candles() -> None:
    """Stochastic with k=14, d=3 needs at least 16 candles."""
    candles = [_make_candle(100.0, idx=i) for i in range(15)]
    with pytest.raises(ValueError, match="need at least 16 candles"):
        compute_stochastic(candles, k_period=14, d_period=3)


def test_compute_stochastic_rejects_invalid_periods() -> None:
    """Periods must be >= 1."""
    candles = [_make_candle(100.0, idx=i) for i in range(20)]
    with pytest.raises(ValueError, match="periods must be >= 1"):
        compute_stochastic(candles, k_period=0, d_period=3)


def test_compute_stochastic_with_uptrend() -> None:
    """Stochastic in uptrend should be high (near 100)."""
    # Strong uptrend with realistic high/low
    candles = []
    for i in range(20):
        close = 100 + i * 2
        candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    k, d = compute_stochastic(candles)

    # In uptrend, %K should be high (close near recent high)
    assert k > 50  # Should be in upper range


def test_compute_stochastic_with_downtrend() -> None:
    """Stochastic in downtrend should be low (near 0)."""
    # Strong downtrend with realistic high/low
    candles = []
    for i in range(20):
        close = 100 - i * 2
        candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    k, d = compute_stochastic(candles)

    # In downtrend, %K should be low (close near recent low)
    assert k < 50  # Should be in lower range


def test_compute_stochastic_returns_0_to_100() -> None:
    """Stochastic values should be between 0 and 100."""
    # Mixed prices
    prices = [100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109]
    candles = [_make_candle(p, high=p + 2, low=p - 2, idx=i) for i, p in enumerate(prices)]

    k, d = compute_stochastic(candles)

    assert 0 <= k <= 100
    assert 0 <= d <= 100


def test_compute_stochastic_deterministic() -> None:
    """Stochastic produces deterministic output given fixed candle data."""
    candles = []
    for i in range(20):
        close = 100 + i * 0.5
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    k1, d1 = compute_stochastic(candles)
    k2, d2 = compute_stochastic(candles)

    assert k1 == k2
    assert d1 == d2


def test_compute_stochastic_with_custom_periods() -> None:
    """Stochastic works with custom periods."""
    candles = []
    for i in range(25):
        close = 100 + i * 0.3
        candles.append(_make_candle(close, high=close + 0.5, low=close - 0.5, idx=i))

    k, d = compute_stochastic(candles, k_period=10, d_period=5)

    # Should compute without error
    assert isinstance(k, float)
    assert isinstance(d, float)
    assert 0 <= k <= 100
    assert 0 <= d <= 100


def test_compute_stochastic_uses_high_low() -> None:
    """Stochastic correctly uses high/low values, not just close."""
    # Create candles where high/low differ significantly from close
    candles = []
    for i in range(20):
        close = 100
        high = 110  # High much higher than close
        low = 90  # Low much lower than close
        candles.append(_make_candle(close, high=high, low=low, idx=i))

    k, d = compute_stochastic(candles)

    # With close in middle of range, %K should be around 50
    assert 40 <= k <= 60


# ========== generate_stochastic_signal tests ==========


def test_generate_stochastic_signal_buy_when_oversold() -> None:
    """BUY signal when %K < oversold threshold."""
    # Create strong downtrend to get low %K
    candles = []
    for i in range(20):
        close = 100 - i * 3
        candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    signal = generate_stochastic_signal(candles, k_period=14, d_period=3, oversold=20, overbought=80)

    assert signal.code == "STOCHASTIC"
    assert signal.side == "BUY"
    assert signal.strength > 0
    assert "oversold" in signal.reason.lower()


def test_generate_stochastic_signal_sell_when_overbought() -> None:
    """SELL signal when %K > overbought threshold."""
    # Create strong uptrend to get high %K
    candles = []
    for i in range(20):
        close = 100 + i * 3
        candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    signal = generate_stochastic_signal(candles, k_period=14, d_period=3, oversold=20, overbought=80)

    assert signal.code == "STOCHASTIC"
    assert signal.side == "SELL"
    assert signal.strength > 0
    assert "overbought" in signal.reason.lower()


def test_generate_stochastic_signal_hold_when_neutral() -> None:
    """HOLD signal when %K is in neutral range."""
    # Create sideways movement
    prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101]
    candles = [_make_candle(p, high=p + 0.5, low=p - 0.5, idx=i) for i, p in enumerate(prices)]

    signal = generate_stochastic_signal(candles, k_period=14, d_period=3, oversold=20, overbought=80)

    assert signal.code == "STOCHASTIC"
    assert signal.side == "HOLD"
    assert signal.strength == 0
    assert "neutral" in signal.reason.lower()


def test_generate_stochastic_signal_includes_k_and_d() -> None:
    """Signal includes both %K and %D values."""
    candles = []
    for i in range(20):
        close = 100 + i * 0.5
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    signal = generate_stochastic_signal(candles)

    # Value should contain both %K and %D
    assert "%K=" in signal.value
    assert "%D=" in signal.value


def test_generate_stochastic_signal_strength_increases_with_extremity() -> None:
    """Signal strength increases as %K moves further from thresholds."""
    # Create two downtrends: moderate and strong
    moderate_candles = []
    for i in range(20):
        close = 100 - i * 1
        moderate_candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    strong_candles = []
    for i in range(20):
        close = 100 - i * 4
        strong_candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    moderate_signal = generate_stochastic_signal(moderate_candles)
    strong_signal = generate_stochastic_signal(strong_candles)

    # Both should be BUY signals (oversold), strong should have higher strength
    if moderate_signal.side == "BUY" and strong_signal.side == "BUY":
        assert strong_signal.strength >= moderate_signal.strength


def test_generate_stochastic_signal_rejects_invalid_thresholds() -> None:
    """Raises error if oversold >= overbought."""
    candles = [_make_candle(100.0, idx=i) for i in range(20)]

    with pytest.raises(ValueError, match="oversold .* must be < overbought"):
        generate_stochastic_signal(candles, oversold=80, overbought=20)


def test_generate_stochastic_signal_rejects_negative_oversold() -> None:
    """Raises error if oversold < 0."""
    candles = [_make_candle(100.0, idx=i) for i in range(20)]

    with pytest.raises(ValueError, match="oversold must be >= 0"):
        generate_stochastic_signal(candles, oversold=-10, overbought=80)


def test_generate_stochastic_signal_rejects_overbought_above_100() -> None:
    """Raises error if overbought > 100."""
    candles = [_make_candle(100.0, idx=i) for i in range(20)]

    with pytest.raises(ValueError, match="overbought must be <= 100"):
        generate_stochastic_signal(candles, oversold=20, overbought=110)


def test_generate_stochastic_signal_with_custom_thresholds() -> None:
    """Works with custom oversold/overbought thresholds."""
    candles = []
    for i in range(20):
        close = 100 + i * 0.3
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    signal = generate_stochastic_signal(candles, oversold=30, overbought=70)

    assert signal.code == "STOCHASTIC"
    assert signal.side in ["BUY", "SELL", "HOLD"]


def test_generate_stochastic_signal_deterministic_output() -> None:
    """Signal generation is deterministic with same inputs."""
    candles = []
    for i in range(20):
        close = 100 + i * 0.5
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    signal1 = generate_stochastic_signal(candles)
    signal2 = generate_stochastic_signal(candles)

    assert signal1.code == signal2.code
    assert signal1.side == signal2.side
    assert signal1.strength == signal2.strength
    assert signal1.value == signal2.value
    assert signal1.reason == signal2.reason
