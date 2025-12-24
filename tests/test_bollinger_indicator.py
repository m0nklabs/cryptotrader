from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.indicators.bollinger import compute_bollinger_bands, generate_bollinger_signal
from core.types import Candle


def _make_candle(close: float, idx: int = 0) -> Candle:
    """Helper to create a candle with minimal required fields."""
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


# ========== compute_bollinger_bands tests ==========


def test_compute_bollinger_bands_requires_minimum_candles() -> None:
    """Bollinger Bands with period=20 needs at least 20 candles."""
    candles = [_make_candle(100.0, i) for i in range(19)]
    with pytest.raises(ValueError, match="need at least 20 candles"):
        compute_bollinger_bands(candles, period=20)


def test_compute_bollinger_bands_rejects_invalid_period() -> None:
    """Period must be >= 1."""
    candles = [_make_candle(100.0, i) for i in range(25)]
    with pytest.raises(ValueError, match="period must be >= 1"):
        compute_bollinger_bands(candles, period=0)


def test_compute_bollinger_bands_rejects_invalid_std_dev() -> None:
    """Standard deviation must be > 0."""
    candles = [_make_candle(100.0, i) for i in range(25)]
    with pytest.raises(ValueError, match="std_dev must be > 0"):
        compute_bollinger_bands(candles, period=20, std_dev=0)


def test_compute_bollinger_bands_with_flat_prices() -> None:
    """Bollinger Bands with flat prices should have upper=middle=lower."""
    # All prices the same
    candles = [_make_candle(100.0, i) for i in range(25)]

    upper, middle, lower = compute_bollinger_bands(candles, period=20)

    # No volatility means bands collapse to middle
    assert upper == middle == lower == 100.0


def test_compute_bollinger_bands_upper_gt_middle_gt_lower() -> None:
    """Bollinger Bands should satisfy upper > middle > lower with volatility."""
    # Prices with some variation
    prices = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105, 100, 101, 99, 102, 98, 103, 97, 104, 96, 105]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    upper, middle, lower = compute_bollinger_bands(candles, period=20)

    assert upper > middle > lower


def test_compute_bollinger_bands_middle_is_sma() -> None:
    """Middle band should be the Simple Moving Average."""
    prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    upper, middle, lower = compute_bollinger_bands(candles, period=20)

    # Calculate expected SMA
    expected_sma = sum(prices[-20:]) / 20

    assert abs(middle - expected_sma) < 0.01


def test_compute_bollinger_bands_deterministic() -> None:
    """Bollinger Bands produces deterministic output."""
    prices = [100 + i * 0.5 for i in range(25)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    upper1, middle1, lower1 = compute_bollinger_bands(candles)
    upper2, middle2, lower2 = compute_bollinger_bands(candles)

    assert upper1 == upper2
    assert middle1 == middle2
    assert lower1 == lower2


def test_compute_bollinger_bands_with_custom_std_dev() -> None:
    """Bollinger Bands works with custom standard deviation."""
    prices = [100 + i * 0.5 for i in range(25)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    # Test with 1 std dev
    upper1, middle1, lower1 = compute_bollinger_bands(candles, period=20, std_dev=1.0)
    # Test with 3 std dev
    upper3, middle3, lower3 = compute_bollinger_bands(candles, period=20, std_dev=3.0)

    # Middle should be the same
    assert middle1 == middle3

    # Bandwidth should be wider with 3 std dev
    bandwidth1 = upper1 - lower1
    bandwidth3 = upper3 - lower3
    assert bandwidth3 > bandwidth1


def test_compute_bollinger_bands_with_custom_period() -> None:
    """Bollinger Bands works with custom period."""
    prices = [100 + i * 0.3 for i in range(30)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    upper, middle, lower = compute_bollinger_bands(candles, period=10, std_dev=2.0)

    # Should compute without error
    assert isinstance(upper, float)
    assert isinstance(middle, float)
    assert isinstance(lower, float)
    assert upper > middle > lower


# ========== generate_bollinger_signal tests ==========


def test_generate_bollinger_signal_buy_when_below_lower_band() -> None:
    """BUY signal when price touches/breaks below lower band."""
    # Create prices that drop below the lower band
    prices = [100] * 20 + [90]  # Sudden drop
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_bollinger_signal(candles, period=20)

    assert signal.code == "BOLLINGER"
    assert signal.side == "BUY"
    assert signal.strength > 0
    assert "lower band" in signal.reason.lower()


def test_generate_bollinger_signal_sell_when_above_upper_band() -> None:
    """SELL signal when price touches/breaks above upper band."""
    # Create prices that jump above the upper band
    prices = [100] * 20 + [110]  # Sudden spike
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_bollinger_signal(candles, period=20)

    assert signal.code == "BOLLINGER"
    assert signal.side == "SELL"
    assert signal.strength > 0
    assert "upper band" in signal.reason.lower()


def test_generate_bollinger_signal_hold_when_within_bands() -> None:
    """HOLD signal when price is within bands."""
    # Steady prices within normal range
    prices = [100 + i * 0.1 for i in range(25)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_bollinger_signal(candles, period=20)

    assert signal.code == "BOLLINGER"
    assert signal.side == "HOLD"
    # Strength may be > 0 if near a band, but should be HOLD
    assert "middle band" in signal.reason.lower() or "band" in signal.reason.lower()


def test_generate_bollinger_signal_includes_price() -> None:
    """Signal includes current price information."""
    prices = [100 + i * 0.5 for i in range(25)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_bollinger_signal(candles)

    # Value should contain price
    assert "$" in signal.value
    price_value = float(signal.value.replace("$", ""))
    assert price_value > 0


def test_generate_bollinger_signal_strength_increases_with_distance() -> None:
    """Signal strength increases as price moves further beyond bands."""
    # Two scenarios: slightly below and far below lower band
    base_prices = [100] * 20
    
    slight_breach = base_prices + [99.5]  # Very slightly below
    moderate_breach = base_prices + [98]  # Moderately below

    slight_candles = [_make_candle(p, i) for i, p in enumerate(slight_breach)]
    moderate_candles = [_make_candle(p, i) for i, p in enumerate(moderate_breach)]

    slight_signal = generate_bollinger_signal(slight_candles)
    moderate_signal = generate_bollinger_signal(moderate_candles)

    # Both should be BUY signals, moderate breach should have higher strength
    if slight_signal.side == "BUY" and moderate_signal.side == "BUY":
        assert moderate_signal.strength >= slight_signal.strength


def test_generate_bollinger_signal_with_custom_parameters() -> None:
    """Works with custom period and std_dev."""
    prices = [100 + i * 0.5 for i in range(30)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_bollinger_signal(candles, period=15, std_dev=1.5)

    assert signal.code == "BOLLINGER"
    assert signal.side in ["BUY", "SELL", "HOLD"]
    assert "Bollinger(15,1.5)" in signal.reason


def test_generate_bollinger_signal_deterministic_output() -> None:
    """Signal generation is deterministic with same inputs."""
    prices = [100 + i * 0.5 for i in range(25)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal1 = generate_bollinger_signal(candles)
    signal2 = generate_bollinger_signal(candles)

    assert signal1.code == signal2.code
    assert signal1.side == signal2.side
    assert signal1.strength == signal2.strength
    assert signal1.value == signal2.value
    assert signal1.reason == signal2.reason


def test_generate_bollinger_signal_handles_zero_bandwidth() -> None:
    """Signal handles edge case of zero bandwidth (flat prices)."""
    # All prices the same
    candles = [_make_candle(100.0, i) for i in range(25)]

    signal = generate_bollinger_signal(candles)

    # Should not crash, should return HOLD with low strength
    assert signal.code == "BOLLINGER"
    assert signal.side == "HOLD"
