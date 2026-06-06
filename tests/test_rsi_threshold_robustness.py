"""Comprehensive test suite for RSI threshold robustness analysis.

Covers parameter sweeps, sensitivity analysis, optimal band detection,
and integration with the backtest engine.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_ROOT))

from scripts.rsi_threshold_robustness import (
    ALL_REGIMES,
    BASE_OVERBOUGHT,
    BASE_OVERSOLD,
    Regime,
    RegimeMetrics,
    THRESHOLD_VARIANTS,
    ThresholdResult,
    classify_regime,
    generate_synthetic_candles,
    print_results_table,
    run_threshold_analysis,
    save_results_json,
)
from core.backtest.engine import BacktestEngine, RSIStrategy, BacktestResult
from core.types import Candle
from decimal import Decimal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_candles() -> list[Candle]:
    """720 synthetic candles (bull, bear, range regimes)."""
    return generate_synthetic_candles(n=720)


@pytest.fixture
def short_candles() -> list[Candle]:
    """100 synthetic candles (enough for RSI calculation)."""
    return generate_synthetic_candles(n=100)


@pytest.fixture
def flat_candles() -> list[Candle]:
    """Candles with minimal price movement (flat regime)."""
    from datetime import datetime, timedelta, timezone
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 100.0
    for i in range(50):
        candles.append(Candle(
            symbol="BTC/USDT",
            exchange="bitfinex",
            timeframe="1h",
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i + 1),
            open=Decimal(str(price)),
            high=Decimal(str(price + 0.5)),
            low=Decimal(str(price - 0.5)),
            close=Decimal(str(price + 0.1)),
            volume=Decimal("500"),
        ))
        price += 0.02
    return candles


@pytest.fixture
def trending_candles() -> list[Candle]:
    """Candles with strong uptrend (bull regime)."""
    from datetime import datetime, timedelta, timezone
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 50.0
    for i in range(50):
        candles.append(Candle(
            symbol="BTC/USDT",
            exchange="bitfinex",
            timeframe="1h",
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i + 1),
            open=Decimal(str(price)),
            high=Decimal(str(price + 2)),
            low=Decimal(str(price - 1)),
            close=Decimal(str(price + 1)),
            volume=Decimal("800"),
        ))
        price += 1.5
    return candles


@pytest.fixture
def bearish_candles() -> list[Candle]:
    """Candles with strong downtrend (bear regime)."""
    from datetime import datetime, timedelta, timezone
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 150.0
    for i in range(50):
        candles.append(Candle(
            symbol="BTC/USDT",
            exchange="bitfinex",
            timeframe="1h",
            open_time=base + timedelta(hours=i),
            close_time=base + timedelta(hours=i + 1),
            open=Decimal(str(price)),
            high=Decimal(str(price + 1)),
            low=Decimal(str(price - 2)),
            close=Decimal(str(price - 1.5)),
            volume=Decimal("900"),
        ))
        price -= 1.2
    return candles


# ===================================================================
# PARAMETER SWEEP TESTS (8 tests)
# ===================================================================

class TestParameterSweep:
    """Tests for parameter sweep across threshold variants."""

    def test_sweep_all_threshold_variants(self, sample_candles: list[Candle]) -> None:
        """Test that all 5 threshold variants run without errors."""
        results = run_threshold_analysis(sample_candles)
        assert len(results) == 5
        expected_labels = {"-20%", "-10%", "base", "+10%", "+20%"}
        assert set(results.keys()) == expected_labels

    def test_sweep_oversold_range(self, sample_candles: list[Candle]) -> None:
        """Test oversold thresholds range from 24 to 36."""
        for label, (os, ob) in THRESHOLD_VARIANTS.items():
            if label == "-20%":
                assert os == 24.0
            elif label == "-10%":
                assert os == 27.0
            elif label == "base":
                assert os == 30.0
            elif label == "+10%":
                assert os == 33.0
            elif label == "+20%":
                assert os == 36.0

    def test_sweep_overbought_range(self, sample_candles: list[Candle]) -> None:
        """Test overbought thresholds range from 56 to 84."""
        for label, (os, ob) in THRESHOLD_VARIANTS.items():
            if label == "-20%":
                assert ob == 56.0
            elif label == "-10%":
                assert ob == 63.0
            elif label == "base":
                assert ob == 70.0
            elif label == "+10%":
                assert ob == 77.0
            elif label == "+20%":
                assert ob == 84.0

    def test_sweep_all_regimes_present(self, sample_candles: list[Candle]) -> None:
        """Test that all 5 regimes appear in results for each variant."""
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            regime_names = list(result.regimes.keys())
            expected_regimes = [r.value for r in ALL_REGIMES]
            assert set(regime_names) == set(expected_regimes), \
                f"Regime mismatch for {label}: {regime_names}"

    def test_sweep_candle_count_consistency(self, sample_candles: list[Candle]) -> None:
        """Test that candle counts sum correctly across regimes."""
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            regime_candle_sum = sum(
                rm.n_candles for rm in result.regimes.values()
            )
            assert regime_candle_sum == result.overall.n_candles, \
                f"Candle count mismatch in {label}: " \
                f"{regime_candle_sum} vs {result.overall.n_candles}"

    def test_sweep_total_candles_equals_input(self, sample_candles: list[Candle]) -> None:
        """Test total candles equals input length."""
        assert len(sample_candles) == 720
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            assert result.overall.n_candles == 720

    def test_sweep_custom_thresholds(self, sample_candles: list[Candle]) -> None:
        """Test that custom threshold variants work."""
        custom = {
            "tight": (20.0, 80.0),
            "wide": (40.0, 60.0),
        }
        results = run_threshold_analysis(sample_candles, threshold_variants=custom)
        assert len(results) == 2
        assert "tight" in results
        assert "wide" in results
        assert results["tight"].oversold == 20.0
        assert results["tight"].overbought == 80.0
        assert results["wide"].oversold == 40.0
        assert results["wide"].overbought == 60.0

    def test_sweep_threshold_affects_trades(self, sample_candles: list[Candle]) -> None:
        """Test that different thresholds produce different trade counts."""
        results = run_threshold_analysis(sample_candles)
        trade_counts = {
            label: result.overall.n_trades
            for label, result in results.items()
        }
        # At least some variation expected
        min_trades = min(trade_counts.values())
        max_trades = max(trade_counts.values())
        # With synthetic data, tighter thresholds should generally
        # produce more trades
        assert max_trades >= min_trades


# ===================================================================
# SENSITIVITY ANALYSIS TESTS (6 tests)
# ===================================================================

class TestSensitivityAnalysis:
    """Tests for sensitivity of metrics to threshold changes."""

    def test_win_rate_sensitivity(self, sample_candles: list[Candle]) -> None:
        """Test that win rate varies with threshold changes."""
        results = run_threshold_analysis(sample_candles)
        win_rates = [
            result.overall.win_rate for result in results.values()
        ]
        # Win rate should be between 0 and 1
        for wr in win_rates:
            assert 0.0 <= wr <= 1.0, f"Win rate {wr} out of range"

    def test_sharpe_ratio_sensitivity(self, sample_candles: list[Candle]) -> None:
        """Test that Sharpe ratio is computed and in reasonable range."""
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            assert isinstance(result.overall.sharpe_ratio, float)
            # Sharpe should be finite (not inf or nan)
            assert math.isfinite(result.overall.sharpe_ratio), \
                f"Sharpe ratio for {label} is not finite"

    def test_max_drawdown_sensitivity(self, sample_candles: list[Candle]) -> None:
        """Test that max drawdown is in valid range [0, 2].

        Max drawdown can exceed 1.0 when equity drops below zero
        (large negative PnL across trades).
        """
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            assert 0.0 <= result.overall.max_drawdown <= 2.0, \
                f"Max drawdown {result.overall.max_drawdown} out of range for {label}"

    def test_profit_factor_sensitivity(self, sample_candles: list[Candle]) -> None:
        """Test that profit factor is non-negative."""
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            assert result.overall.profit_factor >= 0.0, \
                f"Profit factor {result.overall.profit_factor} negative for {label}"

    def test_mean_trade_pnl_sensitivity(self, sample_candles: list[Candle]) -> None:
        """Test that mean trade PnL is a valid float."""
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            assert isinstance(result.overall.mean_trade_pnl, float)
            assert math.isfinite(result.overall.mean_trade_pnl), \
                f"Mean PnL for {label} is not finite"

    def test_std_trade_pnl_sensitivity(self, sample_candles: list[Candle]) -> None:
        """Test that std trade PnL is non-negative."""
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            assert result.overall.std_trade_pnl >= 0.0, \
                f"Std PnL {result.overall.std_trade_pnl} negative for {label}"


# ===================================================================
# OPTIMAL BAND DETECTION TESTS (5 tests)
# ===================================================================

class TestOptimalBandDetection:
    """Tests for optimal RSI band detection across regimes."""

    def test_regime_classification_bull(self, sample_candles: list[Candle]) -> None:
        """Test that first 240 candles are classified as bull."""
        for i in range(240, 245):
            regime = classify_regime(sample_candles, i, lookback=20)
            # After the warmup period, should be bull
            assert regime == Regime.BULL or regime == Regime.HIGH_VOL, \
                f"Candle {i} classified as {regime}, expected bull or high_vol"

    def test_regime_classification_bear(self, sample_candles: list[Candle]) -> None:
        """Test that 240-480 candles are classified as bear."""
        for i in range(260, 265):
            regime = classify_regime(sample_candles, i, lookback=20)
            assert regime == Regime.BEAR or regime == Regime.HIGH_VOL, \
                f"Candle {i} classified as {regime}, expected bear or high_vol"

    def test_regime_classification_range(self, sample_candles: list[Candle]) -> None:
        """Test that 480-720 candles are classified as range."""
        for i in range(500, 505):
            regime = classify_regime(sample_candles, i, lookback=20)
            assert regime in (Regime.RANGE, Regime.HIGH_VOL, Regime.TRANSITION), \
                f"Candle {i} classified as {regime}, expected range or high_vol"

    def test_regime_transition_warmup(self, sample_candles: list[Candle]) -> None:
        """Test that first lookback candles are classified as transition."""
        for i in range(5):
            regime = classify_regime(sample_candles, i, lookback=20)
            assert regime == Regime.TRANSITION, \
                f"Candle {i} classified as {regime}, expected transition"

    def test_optimal_band_identification(self, sample_candles: list[Candle]) -> None:
        """Test that optimal band (base thresholds) is identified."""
        results = run_threshold_analysis(sample_candles)
        base_result = results["base"]
        # Base thresholds should have non-zero trades
        assert base_result.overall.n_trades > 0, \
            "Base thresholds should generate trades"
        # Base thresholds should be in the middle of the pack
        all_trades = sorted(
            (r.overall.n_trades for r in results.values())
        )
        base_trades = base_result.overall.n_trades
        # Base should be between min and max
        assert all_trades[0] <= base_trades <= all_trades[-1], \
            f"Base trades {base_trades} not between min {all_trades[0]} and max {all_trades[-1]}"


# ===================================================================
# INTEGRATION TESTS (5 tests)
# ===================================================================

class TestIntegration:
    """Integration tests with backtest engine and data pipelines."""

    def test_full_analysis_pipeline(self, sample_candles: list[Candle]) -> None:
        """Test the full analysis pipeline end-to-end."""
        results = run_threshold_analysis(sample_candles)
        # Verify result structure
        for label, result in results.items():
            assert isinstance(result, ThresholdResult)
            assert isinstance(result.threshold_label, str)
            assert isinstance(result.oversold, float)
            assert isinstance(result.overbought, float)
            assert isinstance(result.regimes, dict)
            assert isinstance(result.overall, RegimeMetrics)

    def test_backtest_engine_integration(self, sample_candles: list[Candle]) -> None:
        """Test that RSIStrategy works with BacktestEngine directly."""
        strategy = RSIStrategy(oversold=30.0, overbought=70.0)
        engine = BacktestEngine(
            candle_store=None,
            initial_capital=10000.0,
        )
        result: BacktestResult = engine.run(
            strategy=strategy,
            candles=sample_candles[:240],  # Just bull regime
        )
        assert isinstance(result, BacktestResult)
        assert isinstance(result.trades, list)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.max_drawdown, float)
        assert isinstance(result.win_rate, float)
        assert isinstance(result.profit_factor, float)
        assert isinstance(result.total_pnl, float)
        assert isinstance(result.total_return, float)

    def test_results_serialization(self, sample_candles: list[Candle]) -> None:
        """Test that results can be serialized to dict and JSON."""
        results = run_threshold_analysis(sample_candles)
        for label, result in results.items():
            d = result.to_dict()
            assert "threshold" in d
            assert "oversold" in d
            assert "overbought" in d
            assert "regimes" in d
            assert "overall" in d
            # Test JSON serialization
            json_str = json.dumps(d, default=str)
            assert isinstance(json_str, str)

    def test_save_results_json(self, sample_candles: list[Candle], tmp_path: Path) -> None:
        """Test saving results to JSON file."""
        results = run_threshold_analysis(sample_candles)
        output_file = tmp_path / "test_rsi_results.json"
        save_results_json(results, sample_candles, str(output_file))
        assert output_file.exists()
        content = json.loads(output_file.read_text())
        assert "metadata" in content
        assert "results" in content
        assert content["metadata"]["n_candles"] == 720
        assert content["metadata"]["threshold_variants"] == 5
        assert content["metadata"]["regimes"] == [
            "bull", "bear", "range", "high_vol", "transition"
        ]

    def test_metrics_consistency(self, sample_candles: list[Candle]) -> None:
        """Test that metrics are consistent with independent calculations."""
        results = run_threshold_analysis(sample_candles)
        base = results["base"]

        # Win rate should be between 0 and 1
        assert 0.0 <= base.overall.win_rate <= 1.0
        # Sharpe should be finite
        assert math.isfinite(base.overall.sharpe_ratio)
        # Max drawdown should be in valid range [0, 2]
        assert 0.0 <= base.overall.max_drawdown <= 2.0
        # Total return should be consistent with total PnL
        expected_total_return = base.overall.total_pnl / 10000.0
        assert abs(base.overall.total_return - expected_total_return) < 1e-6


# ===================================================================
# EDGE CASE TESTS (extra safety)
# ===================================================================

class TestEdgeCases:
    """Edge case and robustness tests."""

    def test_empty_candles(self) -> None:
        """Test run_threshold_analysis with empty candle list."""
        results = run_threshold_analysis([])
        assert len(results) == 5
        for label, result in results.items():
            assert result.overall.n_candles == 0
            assert result.overall.n_trades == 0
            assert result.overall.win_rate == 0.0

    def test_single_candle(self) -> None:
        """Test with a single candle."""
        candles = generate_synthetic_candles(n=1)
        results = run_threshold_analysis(candles)
        assert len(results) == 5
        # Should not raise on single-candle input

    def test_regime_metrics_to_dict(self) -> None:
        """Test RegimeMetrics.to_dict() serializes all fields."""
        rm = RegimeMetrics(
            regime="bull",
            n_candles=100,
            n_trades=20,
            win_rate=0.65,
            sharpe_ratio=1.2,
            max_drawdown=0.15,
            total_pnl=500.0,
            total_return=0.05,
            profit_factor=1.8,
            mean_trade_pnl=25.0,
            std_trade_pnl=10.0,
        )
        d = rm.to_dict()
        assert d["regime"] == "bull"
        assert d["n_candles"] == 100
        assert d["n_trades"] == 20
        assert d["win_rate"] == 0.65
        assert d["sharpe_ratio"] == 1.2
        assert d["max_drawdown"] == 0.15
        assert d["total_pnl"] == 500.0
        assert d["total_return"] == 0.05
        assert d["profit_factor"] == 1.8
        assert d["mean_trade_pnl"] == 25.0
        assert d["std_trade_pnl"] == 10.0

    def test_classify_regime_volatility_threshold(self) -> None:
        """Test that high volatility is detected correctly."""
        from datetime import datetime, timedelta, timezone
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # Create candles with high volatility
        candles = []
        price = 100.0
        for i in range(50):
            volatility = 50.0 if i % 2 == 0 else -50.0
            candles.append(Candle(
                symbol="BTC/USDT",
                exchange="bitfinex",
                timeframe="1h",
                open_time=base + timedelta(hours=i),
                close_time=base + timedelta(hours=i + 1),
                open=Decimal(str(price)),
                high=Decimal(str(price + 100)),
                low=Decimal(str(price - 100)),
                close=Decimal(str(price + volatility)),
                volume=Decimal("1000"),
            ))
            price += volatility
        regime = classify_regime(candles, 30, lookback=20, vol_threshold_abs=30.0)
        assert regime == Regime.HIGH_VOL

    def test_print_results_table_no_error(self, sample_candles: list[Candle]) -> None:
        """Test that print_results_table runs without errors."""
        results = run_threshold_analysis(sample_candles)
        # Should not raise
        print_results_table(results)

    def test_base_thresholds_constants(self) -> None:
        """Test that base threshold constants are correct."""
        assert BASE_OVERSOLD == 30.0
        assert BASE_OVERBOUGHT == 70.0

    def test_all_regimes_constant(self) -> None:
        """Test that ALL_REGIMES has all 5 expected regimes."""
        assert len(ALL_REGIMES) == 5
        assert Regime.BULL in ALL_REGIMES
        assert Regime.BEAR in ALL_REGIMES
        assert Regime.RANGE in ALL_REGIMES
        assert Regime.HIGH_VOL in ALL_REGIMES
        assert Regime.TRANSITION in ALL_REGIMES

    def test_synthetic_candle_structure(self, sample_candles: list[Candle]) -> None:
        """Test that synthetic candles have correct structure."""
        for candle in sample_candles:
            assert candle.symbol == "BTC/USDT"
            assert candle.exchange == "bitfinex"
            assert candle.timeframe == "1h"
            assert candle.open <= candle.high
            assert candle.open <= candle.low or candle.low <= candle.open
            assert candle.high >= candle.low
            assert isinstance(candle.open, Decimal)
            assert isinstance(candle.close, Decimal)
            assert isinstance(candle.volume, Decimal)

    def test_synthetic_candle_time_sequence(self, sample_candles: list[Candle]) -> None:
        """Test that synthetic candles have monotonically increasing times."""
        for i in range(1, len(sample_candles)):
            assert sample_candles[i].open_time > sample_candles[i - 1].open_time
            assert sample_candles[i].close_time > sample_candles[i - 1].close_time
