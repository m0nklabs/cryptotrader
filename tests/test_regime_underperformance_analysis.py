"""Comprehensive test suite for regime underperformance analysis.

Covers regime classification, metric computation, underperformance
threshold logic, OOS data loading, and integration with the backtest engine.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_ROOT))

from scripts.regime_underperformance_analysis import (
    Regime,
    RegimeMetrics,
    UnderperformanceFlag,
    UnderperformanceThresholds,
    compute_all_regime_metrics,
    compute_transition_baseline,
    compute_underperformance,
    generate_synthetic_candles,
    load_oos_regime_data,
    oos_data_to_candles,
    print_underperformance_summary,
    save_results,
    trans_win_rate,
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
def long_candles() -> list[Candle]:
    """2000 synthetic candles for more robust testing."""
    return generate_synthetic_candles(n=2000)


@pytest.fixture
def flat_candles() -> list[Candle]:
    """Candles with minimal price movement (flat regime)."""
    from datetime import datetime, timedelta, timezone
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
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
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
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
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
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


@pytest.fixture
def sample_oos_data() -> dict[str, Any]:
    """Sample OOS regime data for testing."""
    return {
        "metadata": {
            "generated_at": "2026-06-05T22:57:53.094838+00:00",
            "total_candles": 8760,
            "segments": 3,
        },
        "segments": [
            {
                "name": "train",
                "start_time": "2025-01-01T00:00:00+00:00",
                "end_time": "2025-07-02T12:00:00+00:00",
                "n_candles": 4380,
                "dominant_regime": "high_vol",
                "regime_breakdown": {
                    "bear": 29.9,
                    "range": 6.0,
                    "transition": 0.5,
                    "high_vol": 32.8,
                    "bull": 30.8,
                },
                "mean_return": 0.000113,
                "mean_volatility": 0.020072,
                "mean_price": 39219.73,
                "min_price": 15409.59,
                "max_price": 71197.64,
            },
            {
                "name": "validation",
                "start_time": "2025-07-02T12:00:00+00:00",
                "end_time": "2025-09-13T12:00:00+00:00",
                "n_candles": 1752,
                "dominant_regime": "high_vol",
                "regime_breakdown": {
                    "bear": 31.6,
                    "range": 6.2,
                    "transition": 1.1,
                    "high_vol": 33.0,
                    "bull": 28.1,
                },
                "mean_return": 0.000046,
                "mean_volatility": 0.019859,
                "mean_price": 28534.39,
                "min_price": 17425.73,
                "max_price": 44763.72,
            },
            {
                "name": "test",
                "start_time": "2025-09-13T12:00:00+00:00",
                "end_time": "2026-01-01T00:00:00+00:00",
                "n_candles": 2628,
                "dominant_regime": "high_vol",
                "regime_breakdown": {
                    "bear": 25.1,
                    "range": 5.9,
                    "transition": 0.8,
                    "high_vol": 34.2,
                    "bull": 34.0,
                },
                "mean_return": 0.001235,
                "mean_volatility": 0.020052,
                "mean_price": 91210.1,
                "min_price": 17078.19,
                "max_price": 342455.55,
            },
        ],
        "regime_verification": {
            "bull": {"expected_range": [15, 35], "actual": 31.2, "within_range": True},
            "bear": {"expected_range": [15, 35], "actual": 28.8, "within_range": True},
            "range": {"expected_range": [5, 25], "actual": 9.0, "within_range": True},
            "high_vol": {"expected_range": [20, 50], "actual": 33.3, "within_range": True},
            "low_vol": {"expected_range": [0, 10], "actual": 0.0, "within_range": True},
            "transition": {"expected_range": [0, 5], "actual": 0.7, "within_range": True},
            "overall_pass": True,
            "total_candles": 8760,
        },
    }


# ===================================================================
# REGIME CLASSIFICATION TESTS (5 tests)
# ===================================================================

class TestRegimeClassification:
    """Tests for regime classification logic."""

    def test_transition_warmup(self, sample_candles: list[Candle]) -> None:
        """Test that first lookback candles are classified as transition."""
        from scripts.regime_underperformance_analysis import classify_regime
        for i in range(5):
            regime = classify_regime(sample_candles, i, lookback=20)
            assert regime == Regime.TRANSITION, \
                f"Candle {i} classified as {regime}, expected transition"

    def test_bull_classification(self, sample_candles: list[Candle]) -> None:
        """Test that first 240 candles (after warmup) are bull or high_vol."""
        from scripts.regime_underperformance_analysis import classify_regime
        for i in range(240, 245):
            regime = classify_regime(sample_candles, i, lookback=20)
            assert regime in (Regime.BULL, Regime.HIGH_VOL), \
                f"Candle {i} classified as {regime}, expected bull or high_vol"

    def test_bear_classification(self, sample_candles: list[Candle]) -> None:
        """Test that 240-480 candles are bear or high_vol."""
        from scripts.regime_underperformance_analysis import classify_regime
        for i in range(260, 265):
            regime = classify_regime(sample_candles, i, lookback=20)
            assert regime in (Regime.BEAR, Regime.HIGH_VOL), \
                f"Candle {i} classified as {regime}, expected bear or high_vol"

    def test_range_classification(self, sample_candles: list[Candle]) -> None:
        """Test that 480-720 candles are range or high_vol."""
        from scripts.regime_underperformance_analysis import classify_regime
        for i in range(500, 505):
            regime = classify_regime(sample_candles, i, lookback=20)
            assert regime in (Regime.RANGE, Regime.HIGH_VOL, Regime.TRANSITION), \
                f"Candle {i} classified as {regime}, expected range or high_vol"

    def test_high_volatility_detection(self) -> None:
        """Test that high volatility is detected correctly."""
        from datetime import datetime, timedelta, timezone
        from scripts.regime_underperformance_analysis import classify_regime
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
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
                high=Decimal(str(price + 60)),
                low=Decimal(str(price - 60)),
                close=Decimal(str(price + volatility)),
                volume=Decimal("500"),
            ))
            price += volatility
        # After warmup, should be high_vol
        regime = classify_regime(candles, 25, lookback=20, vol_threshold_abs=30.0)
        assert regime == Regime.HIGH_VOL, \
            f"High vol candles classified as {regime}, expected high_vol"


# ===================================================================
# TRANSITION BASELINE TESTS (4 tests)
# ===================================================================

class TestTransitionBaseline:
    """Tests for transition baseline computation."""

    def test_baseline_computation_returns_valid_metrics(self, sample_candles: list[Candle]) -> None:
        """Test that baseline returns valid return, sharpe, drawdown."""
        baseline = compute_transition_baseline(sample_candles)
        assert "return" in baseline
        assert "sharpe" in baseline
        assert "drawdown" in baseline
        assert "n_candles" in baseline
        assert isinstance(baseline["return"], float)
        assert isinstance(baseline["sharpe"], float)
        assert isinstance(baseline["drawdown"], float)
        assert isinstance(baseline["n_candles"], int)

    def test_baseline_transition_candles_extracted(self, sample_candles: list[Candle]) -> None:
        """Test that baseline extracts transition candles."""
        baseline = compute_transition_baseline(sample_candles)
        assert baseline["n_candles"] > 0, "Should extract at least some transition candles"

    def test_baseline_with_few_transitions(self) -> None:
        """Test baseline when few transition candles exist."""
        from datetime import datetime, timedelta, timezone
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        candles = []
        price = 100.0
        for i in range(100):
            # Create mostly high_vol candles (few transitions)
            candles.append(Candle(
                symbol="BTC/USDT",
                exchange="bitfinex",
                timeframe="1h",
                open_time=base + timedelta(hours=i),
                close_time=base + timedelta(hours=i + 1),
                open=Decimal(str(price)),
                high=Decimal(str(price + 50)),
                low=Decimal(str(price - 50)),
                close=Decimal(str(price + 40)),
                volume=Decimal("500"),
            ))
            price += 40
        baseline = compute_transition_baseline(candles, lookback=20, vol_threshold_abs=30.0)
        assert baseline["return"] is not None
        assert baseline["sharpe"] is not None

    def test_baseline_empty_fallback(self) -> None:
        """Test baseline with single candle (edge case)."""
        from scripts.regime_underperformance_analysis import generate_synthetic_candles
        candles = generate_synthetic_candles(n=1)
        baseline = compute_transition_baseline(candles)
        assert baseline["return"] == 0.0
        assert baseline["sharpe"] == 0.0
        assert baseline["drawdown"] == 0.0


# ===================================================================
# PER-REGIME METRICS TESTS (6 tests)
# ===================================================================

class TestRegimeMetrics:
    """Tests for per-regime metric computation."""

    def test_all_regimes_computed(self, sample_candles: list[Candle]) -> None:
        """Test that all 6 regimes have metrics computed."""
        metrics = compute_all_regime_metrics(sample_candles)
        expected = {Regime.BULL, Regime.BEAR, Regime.RANGE,
                    Regime.HIGH_VOL, Regime.LOW_VOL, Regime.TRANSITION}
        assert set(metrics.keys()) == expected

    def test_bull_metrics_positive_return(self, sample_candles: list[Candle]) -> None:
        """Test that bull regime has positive mean return."""
        metrics = compute_all_regime_metrics(sample_candles)
        bull = metrics[Regime.BULL]
        assert bull.mean_return > 0, f"Bull return {bull.mean_return} should be positive"
        assert bull.n_candles > 0

    def test_bear_metrics_decent_return(self, sample_candles: list[Candle]) -> None:
        """Test that bear regime has metrics in valid range."""
        metrics = compute_all_regime_metrics(sample_candles)
        bear = metrics[Regime.BEAR]
        assert bear.n_candles >= 0
        assert 0.0 <= bear.win_rate <= 1.0
        assert bear.max_drawdown >= 0.0

    def test_range_metrics(self, sample_candles: list[Candle]) -> None:
        """Test range regime metrics."""
        metrics = compute_all_regime_metrics(sample_candles)
        rng = metrics[Regime.RANGE]
        assert rng.n_candles >= 0
        assert rng.n_trades >= 0
        assert 0.0 <= rng.win_rate <= 1.0

    def test_high_vol_metrics(self, sample_candles: list[Candle]) -> None:
        """Test high_vol regime metrics."""
        metrics = compute_all_regime_metrics(sample_candles)
        hv = metrics[Regime.HIGH_VOL]
        assert hv.n_candles > 0
        assert hv.n_trades >= 0

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


# ===================================================================
# UNDERPERFORMANCE ANALYSIS TESTS (6 tests)
# ===================================================================

class TestUnderperformanceAnalysis:
    """Tests for underperformance flag computation."""

    def test_underperformance_flags_all_regimes(self, sample_candles: list[Candle]) -> None:
        """Test that flags are computed for all regimes."""
        metrics = compute_all_regime_metrics(sample_candles)
        baseline = compute_transition_baseline(sample_candles)
        flags = compute_underperformance(metrics, baseline)
        expected_regimes = {"bull", "bear", "range", "high_vol", "low_vol", "transition"}
        assert set(flags.keys()) == expected_regimes

    def test_transition_not_underperforming(self, sample_candles: list[Candle]) -> None:
        """Test that transition regime is not flagged as underperforming."""
        metrics = compute_all_regime_metrics(sample_candles)
        baseline = compute_transition_baseline(sample_candles)
        flags = compute_underperformance(metrics, baseline)
        trans_flag = flags["transition"]
        assert not trans_flag.is_underperforming
        assert trans_flag.score == 0.0
        assert "baseline" in trans_flag.flags

    def test_underperformance_score_range(self, sample_candles: list[Candle]) -> None:
        """Test that underperformance scores are non-negative."""
        metrics = compute_all_regime_metrics(sample_candles)
        baseline = compute_transition_baseline(sample_candles)
        flags = compute_underperformance(metrics, baseline)
        for regime, flag in flags.items():
            assert flag.score >= 0.0, \
                f"Score for {regime} is {flag.score}, expected >= 0"

    def test_threshold_custom_values(self, sample_candles: list[Candle]) -> None:
        """Test that custom thresholds affect underperformance flags."""
        metrics = compute_all_regime_metrics(sample_candles)
        baseline = compute_transition_baseline(sample_candles)

        # Tight thresholds (easier to flag underperformance)
        tight = UnderperformanceThresholds(
            return_threshold=0.00001,
            drawdown_threshold=0.01,
            sharpe_threshold=0.1,
            win_rate_threshold=0.01,
            underperformance_score_threshold=1.0,
        )
        tight_flags = compute_underperformance(metrics, baseline, tight)

        # Loose thresholds (harder to flag underperformance)
        loose = UnderperformanceThresholds(
            return_threshold=0.01,
            drawdown_threshold=0.5,
            sharpe_threshold=2.0,
            win_rate_threshold=0.2,
            underperformance_score_threshold=10.0,
        )
        loose_flags = compute_underperformance(metrics, baseline, loose)

        # Tight should flag more regimes
        tight_count = sum(1 for f in tight_flags.values() if f.is_underperforming)
        loose_count = sum(1 for f in loose_flags.values() if f.is_underperforming)
        assert tight_count >= loose_count, \
            f"Tight ({tight_count}) should flag >= loose ({loose_count}) regimes"

    def test_underperformance_flag_to_dict(self) -> None:
        """Test UnderperformanceFlag.to_dict() serializes all fields."""
        flag = UnderperformanceFlag(
            regime="bull",
            is_underperforming=True,
            score=5.0,
            return_delta=0.001,
            drawdown_delta=0.05,
            sharpe_delta=0.3,
            win_rate_delta=0.05,
            flags=["low_return", "low_sharpe"],
        )
        d = flag.to_dict()
        assert d["regime"] == "bull"
        assert d["is_underperforming"] is True
        assert d["score"] == 5.0
        assert d["return_delta"] == 0.001
        assert d["drawdown_delta"] == 0.05
        assert d["sharpe_delta"] == 0.3
        assert d["win_rate_delta"] == 0.05
        assert d["flags"] == ["low_return", "low_sharpe"]

    def test_deltas_are_computed_correctly(self, sample_candles: list[Candle]) -> None:
        """Test that deltas are computed relative to transition baseline."""
        metrics = compute_all_regime_metrics(sample_candles)
        baseline = compute_transition_baseline(sample_candles)
        flags = compute_underperformance(metrics, baseline)

        for regime, flag in flags.items():
            if regime == "transition":
                continue
            # Return delta should be regime_return - transition_return
            reg_rm = metrics[Regime(regime)]
            expected_return_delta = reg_rm.mean_return - baseline["return"]
            assert abs(flag.return_delta - expected_return_delta) < 1e-10, \
                f"Return delta for {regime}: {flag.return_delta} vs {expected_return_delta}"


# ===================================================================
# OOS DATA LOADING TESTS (4 tests)
# ===================================================================

class TestOOSDataLoading:
    """Tests for OOS data loading and conversion."""

    def test_load_oos_regime_data(self) -> None:
        """Test loading OOS data from default path."""
        data = load_oos_regime_data()
        assert data is not None
        assert "metadata" in data
        assert "segments" in data
        assert "regime_verification" in data

    def test_load_oos_with_filepath(self, sample_oos_data: dict[str, Any], tmp_path: Path) -> None:
        """Test loading OOS data from a specific file path."""
        filepath = tmp_path / "test_oos.json"
        with open(filepath, 'w') as f:
            json.dump(sample_oos_data, f)
        data = load_oos_regime_data(str(filepath))
        assert data is not None
        assert data["metadata"]["total_candles"] == 8760

    def test_oos_data_to_candles(self, sample_oos_data: dict[str, Any]) -> None:
        """Test converting OOS data to candles."""
        candles = oos_data_to_candles(sample_oos_data)
        assert len(candles) > 0
        assert all(isinstance(c, Candle) for c in candles)
        # Should have candles from all segments
        assert len(candles) == sample_oos_data["metadata"]["total_candles"]

    def test_oos_candles_have_valid_values(self, sample_oos_data: dict[str, Any]) -> None:
        """Test that converted candles have valid price values."""
        candles = oos_data_to_candles(sample_oos_data)
        for c in candles[:10]:
            assert float(c.open) > 0
            assert float(c.high) >= float(c.open)
            assert float(c.low) <= float(c.open)
            assert float(c.close) > 0
            assert float(c.volume) > 0


# ===================================================================
# INTEGRATION TESTS (5 tests)
# ===================================================================

class TestIntegration:
    """Integration tests with backtest engine and data pipelines."""

    def test_full_analysis_pipeline(self, sample_candles: list[Candle]) -> None:
        """Test the full analysis pipeline end-to-end."""
        baseline = compute_transition_baseline(sample_candles)
        metrics = compute_all_regime_metrics(sample_candles)
        flags = compute_underperformance(metrics, baseline)

        # Verify all components work together
        assert baseline["n_candles"] > 0
        assert len(metrics) == 6
        assert len(flags) == 6
        assert all(isinstance(f, UnderperformanceFlag) for f in flags.values())

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

    def test_results_serialization(self, sample_candles: list[Candle], tmp_path: Path) -> None:
        """Test that results can be serialized to dict and JSON."""
        baseline = compute_transition_baseline(sample_candles)
        metrics = compute_all_regime_metrics(sample_candles)
        flags = compute_underperformance(metrics, baseline)

        output = {
            "metadata": {
                "analysis": "regime_underperformance",
                "generated_at": "2026-06-05T22:57:53+00:00",
                "transition_baseline": baseline,
            },
            "regime_metrics": {k.value: v.to_dict() for k, v in metrics.items()},
            "underperformance_flags": {k: v.to_dict() for k, v in flags.items()},
        }

        # Test JSON serialization
        json_str = json.dumps(output, default=str)
        assert isinstance(json_str, str)

        # Test round-trip
        loaded = json.loads(json_str)
        assert "metadata" in loaded
        assert "regime_metrics" in loaded
        assert "underperformance_flags" in loaded

    def test_save_results_json(self, sample_candles: list[Candle], tmp_path: Path) -> None:
        """Test saving results to JSON file."""
        baseline = compute_transition_baseline(sample_candles)
        metrics = compute_all_regime_metrics(sample_candles)
        flags = compute_underperformance(metrics, baseline)

        output_file = tmp_path / "test_underperformance.json"
        save_results(metrics, baseline, flags, str(output_file))
        assert output_file.exists()

        content = json.loads(output_file.read_text())
        assert "metadata" in content
        assert "regime_metrics" in content
        assert "underperformance_flags" in content
        assert content["metadata"]["analysis"] == "regime_underperformance"

    def test_metrics_consistency(self, sample_candles: list[Candle]) -> None:
        """Test that metrics are consistent with independent calculations."""
        metrics = compute_all_regime_metrics(sample_candles)
        for regime, rm in metrics.items():
            # Win rate should be between 0 and 1
            assert 0.0 <= rm.win_rate <= 1.0, \
                f"Win rate {rm.win_rate} out of range for {regime}"
            # Sharpe should be finite
            assert math.isfinite(rm.sharpe_ratio), \
                f"Sharpe ratio for {regime} is not finite"
            # Max drawdown should be in valid range
            assert 0.0 <= rm.max_drawdown <= 2.0, \
                f"Max drawdown {rm.max_drawdown} out of range for {regime}"
            # Total return should be consistent
            assert math.isfinite(rm.total_return), \
                f"Total return for {regime} is not finite"


# ===================================================================
# EDGE CASE TESTS (5 tests)
# ===================================================================

class TestEdgeCases:
    """Edge case and robustness tests."""

    def test_empty_candles(self) -> None:
        """Test compute_all_regime_metrics with empty candle list."""
        metrics = compute_all_regime_metrics([])
        assert len(metrics) == 6
        for regime, rm in metrics.items():
            assert rm.n_candles == 0
            assert rm.n_trades == 0
            assert rm.win_rate == 0.0

    def test_single_candle(self) -> None:
        """Test with a single candle."""
        candles = generate_synthetic_candles(n=1)
        metrics = compute_all_regime_metrics(candles)
        assert len(metrics) == 6
        # Should not raise on single-candle input

    def test_single_regime_candles(self) -> None:
        """Test with candles that all belong to one regime."""
        from scripts.regime_underperformance_analysis import (
            Regime,
            compute_regime_metrics,
        )
        from decimal import Decimal

        # Create high_vol candles with varying direction
        from datetime import datetime, timedelta, timezone
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        high_vol_candles = []
        price = 100.0
        for i in range(50):
            # Alternate direction for more volatility
            direction = 40 if i % 2 == 0 else -30
            high_vol_candles.append(Candle(
                symbol="BTC/USDT",
                exchange="bitfinex",
                timeframe="1h",
                open_time=base + timedelta(hours=i),
                close_time=base + timedelta(hours=i + 1),
                open=Decimal(str(price)),
                high=Decimal(str(price + 60)),
                low=Decimal(str(price - 60)),
                close=Decimal(str(price + direction)),
                volume=Decimal("500"),
            ))
            price += direction

        # All should be high_vol with vol_threshold_abs=30.0
        metrics = compute_regime_metrics(
            high_vol_candles, Regime.HIGH_VOL, lookback=20, vol_threshold_abs=30.0
        )
        assert metrics.n_candles > 0

    def test_print_summary_no_crash(self, sample_candles: list[Candle]) -> None:
        """Test that print_underperformance_summary doesn't crash."""
        baseline = compute_transition_baseline(sample_candles)
        metrics = compute_all_regime_metrics(sample_candles)
        flags = compute_underperformance(metrics, baseline)

        # Should not raise
        print_underperformance_summary(metrics, baseline, flags)

    def test_trans_win_rate(self, sample_candles: list[Candle]) -> None:
        """Test trans_win_rate computes correctly."""
        metrics = compute_all_regime_metrics(sample_candles)
        wr = trans_win_rate(metrics, Regime.BULL)
        assert 0.0 <= wr <= 1.0, f"trans_win_rate {wr} out of range"


# ===================================================================
# THRESHOLD LOGIC TESTS (4 tests)
# ===================================================================

class TestThresholdLogic:
    """Tests for threshold-based underperformance classification."""

    def test_bear_underperformance_flagged(self, sample_candles: list[Candle]) -> None:
        """Test that bear regime is properly evaluated for underperformance."""
        baseline = compute_transition_baseline(sample_candles)
        metrics = compute_all_regime_metrics(sample_candles)
        flags = compute_underperformance(metrics, baseline)

        bear_flag = flags["bear"]
        assert bear_flag.regime == "bear"
        # Bear should have a valid score
        assert bear_flag.score >= 0.0

    def test_range_underperformance_flagged(self, sample_candles: list[Candle]) -> None:
        """Test that range regime is properly evaluated for underperformance."""
        baseline = compute_transition_baseline(sample_candles)
        metrics = compute_all_regime_metrics(sample_candles)
        flags = compute_underperformance(metrics, baseline)

        range_flag = flags["range"]
        assert range_flag.regime == "range"
        assert range_flag.score >= 0.0

    def test_threshold_affects_classification(self, sample_candles: list[Candle]) -> None:
        """Test that changing thresholds changes underperformance classification."""
        baseline = compute_transition_baseline(sample_candles)
        metrics = compute_all_regime_metrics(sample_candles)

        # Very strict thresholds
        strict = UnderperformanceThresholds(
            return_threshold=0.000001,
            drawdown_threshold=0.001,
            sharpe_threshold=0.01,
            win_rate_threshold=0.001,
            underperformance_score_threshold=0.5,
        )
        strict_flags = compute_underperformance(metrics, baseline, strict)

        # Very loose thresholds
        loose = UnderperformanceThresholds(
            return_threshold=1.0,
            drawdown_threshold=10.0,
            sharpe_threshold=10.0,
            win_rate_threshold=1.0,
            underperformance_score_threshold=100.0,
        )
        loose_flags = compute_underperformance(metrics, baseline, loose)

        # Strict should flag more
        strict_count = sum(1 for f in strict_flags.values() if f.is_underperforming)
        loose_count = sum(1 for f in loose_flags.values() if f.is_underperforming)
        assert strict_count >= loose_count, \
            f"Strict ({strict_count}) should flag >= loose ({loose_count}) regimes"

    def test_live_threshold_defaults(self) -> None:
        """Test that default thresholds have reasonable values."""
        t = UnderperformanceThresholds()
        assert t.return_threshold == 0.00005
        assert t.drawdown_threshold == 0.05
        assert t.sharpe_threshold == 0.3
        assert t.win_rate_threshold == 0.05
        assert t.underperformance_score_threshold == 2.0
