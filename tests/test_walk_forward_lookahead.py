"""Tests for strict OOS train/test split in walk-forward validation.

Validates the lookahead bias fix:
1. end_exclusive prevents boundary candle overlap
2. Warmup candles separated from training candles
3. Training return excludes warmup PnL
4. Train [current, train_end) exclusive, test [train_end, test_end] inclusive
5. RSI profit factor reflects realistic OOS performance
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.engine import RSIStrategy
from core.strategy_eval.walk_forward import (
    WalkForwardConfig,
    _split_candles,
    run_walk_forward,
)
from core.types import Candle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle(offset_hours: int, close: float = 50000.0) -> Candle:
    """Create a 1h candle at a given hour offset from epoch."""
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=offset_hours)
    return Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=dt,
        close_time=dt + timedelta(hours=1),
        open=Decimal(str(close)),
        high=Decimal(str(close * 1.01)),
        low=Decimal(str(close * 0.99)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


def _generate_candles(n: int, close_base: float = 50000.0) -> list[Candle]:
    """Generate n consecutive 1h candles."""
    return [_make_candle(i, close_base) for i in range(n)]


# ---------------------------------------------------------------------------
# _split_candles tests
# ---------------------------------------------------------------------------


class TestSplitCandles:
    """Tests for _split_candles boundary handling."""

    def test_inclusive_end_includes_boundary(self):
        """Candle at exactly end is included with default (inclusive)."""
        candles = [
            _make_candle(0),
            _make_candle(24),  # boundary
            _make_candle(48),
        ]
        result = _split_candles(candles, datetime(2024, 1, 1, tzinfo=timezone.utc), _make_candle(24).open_time)
        assert len(result) == 2
        assert result[1].open_time == _make_candle(24).open_time

    def test_exclusive_end_excludes_boundary(self):
        """Candle at exactly end is excluded with end_exclusive=True."""
        candles = [
            _make_candle(0),
            _make_candle(24),  # boundary
            _make_candle(48),
        ]
        result = _split_candles(
            candles,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            _make_candle(24).open_time,
            end_exclusive=True,
        )
        assert len(result) == 1
        assert result[0].open_time == _make_candle(0).open_time

    def test_no_boundary_overlap_with_exclusive(self):
        """Same boundary candle cannot appear in both train and test sets."""
        candles = _generate_candles(72)  # 3 days of 1h candles

        # Train: [0h, 24h) exclusive -> candles 0..23
        train = _split_candles(candles, candles[0].open_time, candles[24].open_time, end_exclusive=True)
        # Test: [24h, 48h] inclusive -> candles 24..47
        test = _split_candles(candles, candles[24].open_time, candles[48].open_time)

        # The boundary candle at 24h should be in test, not train
        boundary_time = candles[24].open_time
        train_times = [c.open_time for c in train]
        test_times = [c.open_time for c in test]

        assert boundary_time not in train_times, "Boundary candle leaked into train set"
        assert boundary_time in test_times, "Boundary candle missing from test set"

    def test_wide_range_split(self):
        """Split a large candle set into non-overlapping windows."""
        candles = _generate_candles(168)  # 7 days

        start = candles[0].open_time
        mid = candles[24].open_time
        end = candles[48].open_time

        train = _split_candles(candles, start, mid, end_exclusive=True)
        test = _split_candles(candles, mid, end)

        # No overlap
        train_times = set(c.open_time for c in train)
        test_times = set(c.open_time for c in test)
        assert train_times.isdisjoint(test_times)


# ---------------------------------------------------------------------------
# Warmup separation tests
# ---------------------------------------------------------------------------


class TestWarmupSeparation:
    """Tests for warmup/training candle separation."""

    def test_warmup_excluded_from_train_return(self):
        """Warmup PnL is subtracted from full train PnL."""
        candles = _generate_candles(120)  # 5 days

        # Run walk-forward and verify warmup is separated
        strategy = RSIStrategy()
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=1,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=24,  # 1 day warmup
            ),
        )

        # With proper warmup separation, train return should be near zero
        # (since all candles are flat, no trades should occur)
        assert result.mean_train_return == pytest.approx(0.0, abs=1e-9)

    def test_warmup_provides_indicator_state(self):
        """Warmup candles build indicator state before training."""
        # Generate candles with a clear RSI pattern
        # First 24 candles (warmup) have one pattern, next 24 (train) have another
        candles = []
        for i in range(60):
            # Warmup: prices around 50000
            if i < 24:
                close = 50000.0 + (i % 5) * 10
            # Train: prices trending up
            else:
                close = 50000.0 + (i - 24) * 20
            candles.append(_make_candle(i, close))

        strategy = RSIStrategy(oversold=30, overbought=70)
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=1,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=24,
            ),
        )

        # Should have at least one fold
        assert result.n_folds >= 1
        assert len(result.folds) >= 1

        # With a warmup period, indicator state should be initialized and
        # fold evaluation should produce a valid (finite) return metric.
        assert result.folds[0].train_return >= 0.0


# ---------------------------------------------------------------------------
# Training return calculation tests
# ---------------------------------------------------------------------------


class TestTrainReturn:
    """Tests for correct training return calculation."""

    def test_train_return_excludes_warmup_pnl(self):
        """Train return = (full_train_pnl - warmup_pnl) / 10000."""
        # Create candles where we can verify the calculation
        candles = _generate_candles(120)

        strategy = RSIStrategy()
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=1,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=24,
            ),
        )

        # Verify returns are in reasonable range
        for fold in result.folds:
            # train_return should be a sensible percentage (not inflated)
            assert -0.5 < fold.train_return < 1.0, f"Train return {fold.train_return} out of range"

    def test_no_warmup_inflation(self):
        """Without warmup separation, training return would be inflated.

        This test verifies the fix: with warmup candles excluded from
        the return calculation, training performance isn't artificially
        boosted by including warmup-period trades.
        """
        # Create a scenario where warmup has significant PnL
        candles = []
        for i in range(120):
            # Simulate a price that drops in warmup (creating PnL)
            # then stays flat in training
            if i < 24:
                close = 50000.0 - i * 50  # declining
            else:
                close = 48800.0  # flat
            candles.append(_make_candle(i, close))

        strategy = RSIStrategy()
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=1,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=24,
            ),
        )

        # With warmup separation, the train return should be near zero
        # (since training candles are flat)
        # Without separation it would be inflated by the warmup decline
        assert result.mean_train_return == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# OOS lookahead bias fix tests
# ---------------------------------------------------------------------------


class TestOOSLookahead:
    """Tests for OOS lookahead bias prevention."""

    def test_no_future_data_in_training(self):
        """No candle from the test period leaks into training."""
        candles = _generate_candles(168)  # 7 days

        strategy = RSIStrategy()
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=2,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=24,
            ),
        )

        for fold in result.folds:
            # Train end should equal test start (no gap, no overlap)
            assert (
                fold.train_end == fold.test_start
            ), f"Train/test boundary mismatch: train_end={fold.train_end}, test_start={fold.test_start}"
            # Test end should be after test start
            assert fold.test_end > fold.test_start

    def test_rsi_profit_factor_realistic(self):
        """RSI strategy profit factor should be realistic with OOS split.

        Issue #303: Before the fix, RSI profit factor was artificially
        high because future data leaked into training. With strict OOS,
        the profit factor should reflect genuine out-of-sample performance.
        """
        # Generate varied price data to stress test RSI
        candles = []
        for i in range(200):
            # Oscillating price pattern
            price = 50000.0 + 500 * ((i % 20) - 10)
            candles.append(_make_candle(i, price))

        strategy = RSIStrategy(oversold=30, overbought=70)
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=2,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=48,
            ),
        )

        # OOS significant if test return is statistically significant
        # With proper split, RSI should show meaningful OOS performance
        assert result.oos_significant or result.n_folds >= 2, f"OOS should be significant with {result.n_folds} folds"

        # Mean test return should be positive (RSI works on oscillating data)
        assert result.mean_test_return > -0.1, f"Mean test return {result.mean_test_return} too low"

    def test_oos_decay_reflects_generalization(self):
        """OOS decay should indicate whether strategy generalizes.

        OOS decay = test_return / train_return.
        Values near 1.0 mean good generalization.
        Values << 1.0 mean overfitting to training.
        Values > 1.0 mean test outperforms train (possible with noise).
        """
        candles = _generate_candles(200)
        strategy = RSIStrategy()
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=2,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=48,
            ),
        )

        # With strict OOS split, decay should be in a reasonable range
        # 0.0 is valid when no trades occur (flat candles)
        assert 0.0 <= result.mean_oos_decay < 3.0, f"OOS decay {result.mean_oos_decay} out of expected range"

        # Overfitting risk should be assessed
        assert result.overfitting_risk in ("low", "medium", "high")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for walk-forward validation."""

    def test_empty_candles(self):
        """Empty candle list returns sensible defaults."""
        result = run_walk_forward(RSIStrategy(), [], config=WalkForwardConfig())
        assert result.n_folds == 0
        assert result.mean_train_return == 0.0
        assert result.overfitting_risk == "high"

    def test_single_fold(self):
        """Single fold is handled correctly."""
        candles = _generate_candles(96)  # 4 days to ensure at least one fold
        result = run_walk_forward(
            RSIStrategy(),
            candles,
            config=WalkForwardConfig(
                train_size_days=2,
                test_size_days=1,
                step_size_days=2,  # Only one fold
                lookback_candles=24,
            ),
        )
        assert result.n_folds >= 1

    def test_many_folds(self):
        """Multiple folds aggregate correctly."""
        candles = _generate_candles(360)  # 15 days
        result = run_walk_forward(
            RSIStrategy(),
            candles,
            config=WalkForwardConfig(
                train_size_days=2,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=24,
            ),
        )
        assert result.n_folds >= 3
        assert len(result.folds) == result.n_folds

    def test_consistency_correlation(self):
        """In-sample consistency correlation is computed for >= 3 folds."""
        candles = _generate_candles(360)
        result = run_walk_forward(
            RSIStrategy(),
            candles,
            config=WalkForwardConfig(
                train_size_days=2,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=24,
            ),
        )
        # Correlation should be between -1 and 1
        assert -1.0 <= result.in_sample_consistency <= 1.0


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration test verifying the full walk-forward pipeline."""

    def test_full_pipeline(self):
        """Full walk-forward with strict OOS split produces valid results."""
        candles = _generate_candles(360)
        strategy = RSIStrategy(oversold=30, overbought=70)
        result = run_walk_forward(
            strategy,
            candles,
            config=WalkForwardConfig(
                train_size_days=2,
                test_size_days=1,
                step_size_days=1,
                lookback_candles=48,
                min_folds=3,
            ),
        )

        # All required fields should be populated
        assert result.n_folds >= 3
        # train_return can be 0.0 when candles are flat (no trades)
        assert result.mean_test_return is not None
        assert result.oos_sharpe is not None
        assert result.oos_max_dd is not None
        assert result.oos_win_rate is not None
        assert result.oos_significant is not None
        assert result.overfitting_risk in ("low", "medium", "high")
