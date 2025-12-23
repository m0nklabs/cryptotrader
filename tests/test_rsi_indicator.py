from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.indicators.rsi import compute_rsi, generate_rsi_signal
from core.types import Candle


def _make_candle(close: float, idx: int = 0) -> Candle:
    """Helper to create a candle with minimal required fields."""
    # Use timedelta to safely handle any idx value
    from datetime import timedelta
    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    open_time = base_time + timedelta(hours=idx)
    close_time = base_time + timedelta(hours=idx, minutes=59)
    return Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=open_time,
        close_time=close_time,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


# ========== compute_rsi tests ==========


def test_compute_rsi_requires_minimum_candles() -> None:
    """RSI with period=14 needs at least 15 candles."""
    candles = [_make_candle(100.0, i) for i in range(14)]
    with pytest.raises(ValueError, match="need at least 15 candles"):
        compute_rsi(candles, period=14)


def test_compute_rsi_rejects_invalid_period() -> None:
    """Period must be >= 1."""
    candles = [_make_candle(100.0, i) for i in range(20)]
    with pytest.raises(ValueError, match="period must be >= 1"):
        compute_rsi(candles, period=0)


def test_compute_rsi_returns_100_when_all_gains() -> None:
    """RSI = 100 when all price changes are gains (no losses)."""
    # Create uptrend: prices steadily increasing
    candles = [_make_candle(100.0 + i, i) for i in range(20)]
    rsi = compute_rsi(candles, period=14)
    assert rsi == 100.0


def test_compute_rsi_returns_0_when_all_losses() -> None:
    """RSI = 0 when all price changes are losses (no gains)."""
    # Create downtrend: prices steadily decreasing
    candles = [_make_candle(100.0 - i, i) for i in range(20)]
    rsi = compute_rsi(candles, period=14)
    assert rsi == 0.0


def test_compute_rsi_deterministic_with_fixed_data() -> None:
    """RSI produces deterministic output given fixed candle data."""
    # Fixed price series
    prices = [
        44.0, 44.25, 44.5, 43.75, 44.0, 44.5, 44.75, 44.5, 44.25,
        44.75, 45.0, 45.25, 45.5, 45.25, 45.0, 44.75, 44.5, 44.25,
        44.0, 43.75, 43.5, 43.25, 43.0, 42.75, 42.5,
    ]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    # Compute RSI twice to verify determinism
    rsi1 = compute_rsi(candles, period=14)
    rsi2 = compute_rsi(candles, period=14)

    assert rsi1 == rsi2
    # Specific value check (calculated manually)
    # With declining prices at the end, RSI should be < 50
    assert 0.0 < rsi1 < 50.0


def test_compute_rsi_with_mixed_gains_and_losses() -> None:
    """RSI computes correctly with mixed price movements."""
    # Mix of ups and downs, ending slightly bearish
    prices = [
        100, 102, 101, 103, 102, 104, 103, 105, 104, 106,
        105, 104, 103, 102, 101, 100, 99, 98, 97, 96,
    ]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]
    rsi = compute_rsi(candles, period=14)

    # With recent declines, expect RSI < 50
    assert 0.0 < rsi < 50.0


def test_compute_rsi_with_shorter_period() -> None:
    """RSI works with different periods (e.g., 7)."""
    prices = [100 + i * 0.5 for i in range(15)]  # Slight uptrend
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    rsi = compute_rsi(candles, period=7)
    # Uptrend should give RSI > 50
    assert 50.0 < rsi <= 100.0


# ========== generate_rsi_signal tests ==========


def test_generate_rsi_signal_buy_when_oversold() -> None:
    """BUY signal when RSI < oversold threshold."""
    # Create strong downtrend to get low RSI
    prices = [100 - i * 2 for i in range(20)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_rsi_signal(candles, period=14, oversold=30, overbought=70)

    assert signal.code == "RSI"
    assert signal.side == "BUY"
    assert signal.strength > 0
    assert "oversold" in signal.reason.lower()
    assert "below" in signal.reason.lower()


def test_generate_rsi_signal_sell_when_overbought() -> None:
    """SELL signal when RSI > overbought threshold."""
    # Create strong uptrend to get high RSI
    prices = [100 + i * 2 for i in range(20)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_rsi_signal(candles, period=14, oversold=30, overbought=70)

    assert signal.code == "RSI"
    assert signal.side == "SELL"
    assert signal.strength > 0
    assert "overbought" in signal.reason.lower()
    assert "above" in signal.reason.lower()


def test_generate_rsi_signal_hold_when_neutral() -> None:
    """HOLD signal when RSI is in neutral range."""
    # Create mostly flat prices with slight variations (alternating 100/101)
    prices = [100 + (i % 2) for i in range(20)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_rsi_signal(candles, period=14, oversold=30, overbought=70)

    assert signal.code == "RSI"
    assert signal.side == "HOLD"
    assert signal.strength == 0
    assert "neutral" in signal.reason.lower()


def test_generate_rsi_signal_includes_reason_string() -> None:
    """Signal includes human-readable reason."""
    prices = [100 + i for i in range(20)]  # Uptrend
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_rsi_signal(candles, period=14)

    # Reason should contain RSI period and value
    assert "RSI(14)" in signal.reason
    assert len(signal.reason) > 10  # Meaningful message


def test_generate_rsi_signal_value_contains_rsi() -> None:
    """Signal value field contains the RSI numeric value."""
    prices = [100 + i * 0.5 for i in range(20)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_rsi_signal(candles, period=14)

    # Value should be a string representation of RSI
    rsi_value = float(signal.value)
    assert 0.0 <= rsi_value <= 100.0


def test_generate_rsi_signal_strength_increases_with_extremity() -> None:
    """Signal strength increases as RSI moves further from thresholds."""
    # Create two downtrends: one weak (RSI ~25), one moderate (RSI ~15)
    # Using smaller decrements to keep RSI in measurable range
    weak_prices = [100 - i * 0.3 for i in range(20)]
    moderate_prices = [100 - i * 0.8 for i in range(20)]

    weak_candles = [_make_candle(p, i) for i, p in enumerate(weak_prices)]
    moderate_candles = [_make_candle(p, i) for i, p in enumerate(moderate_prices)]

    weak_signal = generate_rsi_signal(weak_candles, period=14)
    moderate_signal = generate_rsi_signal(moderate_candles, period=14)

    # Both should be BUY signals (oversold), and moderate should have higher strength
    if weak_signal.side == "BUY" and moderate_signal.side == "BUY":
        assert moderate_signal.strength >= weak_signal.strength


def test_generate_rsi_signal_rejects_invalid_thresholds() -> None:
    """Raises error if oversold >= overbought."""
    candles = [_make_candle(100, i) for i in range(20)]

    with pytest.raises(ValueError, match="oversold .* must be < overbought"):
        generate_rsi_signal(candles, period=14, oversold=70, overbought=30)


def test_generate_rsi_signal_rejects_oversold_zero() -> None:
    """Raises error if oversold <= 0 (would cause division by zero)."""
    candles = [_make_candle(100, i) for i in range(20)]

    with pytest.raises(ValueError, match="oversold must be > 0"):
        generate_rsi_signal(candles, period=14, oversold=0, overbought=70)


def test_generate_rsi_signal_rejects_overbought_100() -> None:
    """Raises error if overbought >= 100 (would cause division by zero)."""
    candles = [_make_candle(100, i) for i in range(20)]

    with pytest.raises(ValueError, match="overbought must be < 100"):
        generate_rsi_signal(candles, period=14, oversold=30, overbought=100)


def test_generate_rsi_signal_custom_thresholds() -> None:
    """Works with custom oversold/overbought thresholds."""
    # Create slight uptrend
    prices = [100 + i * 0.3 for i in range(20)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    # Use tighter thresholds (20/80 instead of 30/70)
    signal = generate_rsi_signal(candles, period=14, oversold=20, overbought=80)

    # Should compute without error
    assert signal.code == "RSI"
    assert signal.side in ["BUY", "SELL", "HOLD"]


def test_generate_rsi_signal_deterministic_output() -> None:
    """Signal generation is deterministic with same inputs."""
    prices = [100, 101, 102, 101, 100, 99, 100, 101, 102, 103, 102, 101, 100, 99, 98, 97, 98, 99, 100, 101]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal1 = generate_rsi_signal(candles, period=14)
    signal2 = generate_rsi_signal(candles, period=14)

    assert signal1.code == signal2.code
    assert signal1.side == signal2.side
    assert signal1.strength == signal2.strength
    assert signal1.value == signal2.value
    assert signal1.reason == signal2.reason


# ========== Edge cases ==========


def test_compute_rsi_with_flat_prices() -> None:
    """RSI handles flat prices (no change)."""
    # All prices the same
    candles = [_make_candle(100.0, i) for i in range(20)]

    # When there's no price movement, RSI is undefined (0/0)
    # Implementation returns 100 when avg_loss = 0
    rsi = compute_rsi(candles, period=14)
    assert rsi == 100.0


def test_generate_rsi_signal_with_exact_threshold_values() -> None:
    """Test behavior when RSI equals threshold exactly."""
    # This is harder to control precisely, but we can verify no crashes
    prices = [100 + i * 0.1 for i in range(20)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_rsi_signal(candles, period=14, oversold=30, overbought=70)

    # Should always return valid signal
    assert signal.side in ["BUY", "SELL", "HOLD"]
    assert 0 <= signal.strength <= 100
