"""Tests for RSI threshold robustness analysis."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.rsi_threshold_robustness import (
    DEFAULT_OVERSOLD,
    DEFAULT_OVERBOUGHT,
    PCT_10_OVERSOLD,
    PCT_10_OVERBOUGHT,
    PCT_20_OVERSOLD,
    PCT_20_OVERBOUGHT,
    RSIResult,
    RegimeSensitivity,
    analyze_sensitivity,
    calculate_profit_factor_from_pnl,
    find_optimal_rsi_bands,
    run_rsi_sweep,
    save_results,
)
from core.types import Candle
from scripts.walk_forward_analysis import Regime, generate_synthetic_candles


class TestRSISweep:
    """Tests for RSI threshold sweep."""

    def test_sweep_returns_results(self):
        """Sweep should return results for each regime x threshold combo."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        assert len(results) > 0
        assert all(isinstance(r, RSIResult) for r in results)

    def test_sweep_covers_all_regimes(self):
        """Sweep should cover all regimes present in data."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        regimes = {r.regime for r in results}
        assert "bull" in regimes
        assert "bear" in regimes
        assert "range" in regimes
        assert "high_vol" in regimes

    def test_sweep_thresholds_are_correct(self):
        """Sweep should use correct oversold/overbought values."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        for r in results:
            assert r.oversold in PCT_20_OVERSOLD
            assert r.overbought in PCT_20_OVERBOUGHT
            assert r.oversold < r.overbought

    def test_sweep_with_custom_thresholds(self):
        """Sweep should accept custom threshold values."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(
            candles,
            oversold_values=[25.0, 35.0],
            overbought_values=[65.0, 75.0],
        )
        assert len(results) > 0
        for r in results:
            assert r.oversold in [25.0, 35.0]
            assert r.overbought in [65.0, 75.0]

    def test_sweep_default_thresholds(self):
        """Default thresholds should be 30/70."""
        assert DEFAULT_OVERSOLD == 30.0
        assert DEFAULT_OVERBOUGHT == 70.0

    def test_sweep_pct_ranges(self):
        """±10% and ±20% ranges should be correct."""
        assert PCT_10_OVERSOLD == [27.0, 30.0, 33.0]
        assert PCT_10_OVERBOUGHT == [63.0, 70.0, 77.0]
        assert PCT_20_OVERSOLD == [24.0, 27.0, 30.0, 33.0, 36.0]
        assert PCT_20_OVERBOUGHT == [56.0, 63.0, 70.0, 77.0, 84.0]

    def test_sweep_result_fields(self):
        """RSIResult should have all required fields."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        r = results[0]
        assert hasattr(r, "regime")
        assert hasattr(r, "oversold")
        assert hasattr(r, "overbought")
        assert hasattr(r, "win_rate")
        assert hasattr(r, "sharpe_ratio")
        assert hasattr(r, "max_drawdown")
        assert hasattr(r, "n_trades")
        assert hasattr(r, "profit_factor")

    def test_sweep_bull_regime_positive_sharpe(self):
        """Bull regime should generally have positive Sharpe."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        bull_results = [r for r in results if r.regime == "bull"]
        if bull_results:
            mean_sharpe = sum(r.sharpe_ratio for r in bull_results) / len(bull_results)
            assert mean_sharpe > 0

    def test_sweep_many_candles(self):
        """Sweep should handle larger candle sets."""
        candles = generate_synthetic_candles(n=1440)
        results = run_rsi_sweep(candles)
        assert len(results) > 0


class TestSensitivityAnalysis:
    """Tests for sensitivity analysis."""

    def test_analyze_returns_dict(self):
        """analyze_sensitivity should return a dict."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        assert isinstance(sensitivity, dict)

    def test_analyze_all_regimes(self):
        """Should analyze all regimes with results."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        assert len(sensitivity) > 0

    def test_sensitivity_fields(self):
        """RegimeSensitivity should have all required fields."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        for regime, s in sensitivity.items():
            assert isinstance(s, RegimeSensitivity)
            assert s.regime == regime
            assert s.best_oversold > 0
            assert s.best_overbought > s.best_oversold
            assert s.sharpe_range >= 0
            assert s.win_rate_range >= 0
            assert s.max_dd_range >= 0

    def test_sensitivity_best_by_sharpe(self):
        """Best values should be the ones with highest Sharpe."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        for regime, s in sensitivity.items():
            regime_results = [r for r in results if r.regime == regime]
            if regime_results:
                best_sharpe_result = max(regime_results, key=lambda r: r.sharpe_ratio)
                assert s.best_sharpe == best_sharpe_result.sharpe_ratio
                assert s.best_oversold == best_sharpe_result.oversold
                assert s.best_overbought == best_sharpe_result.overbought


class TestOptimalBands:
    """Tests for optimal RSI band finding."""

    def test_find_optimal_returns_dict(self):
        """find_optimal_rsi_bands should return a dict."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        pct10 = [r for r in results if r.oversold in PCT_10_OVERSOLD and r.overbought in PCT_10_OVERBOUGHT]
        optimal = find_optimal_rsi_bands(sensitivity, pct10, results)
        assert isinstance(optimal, dict)

    def test_optimal_bands_have_fields(self):
        """Optimal bands should have all required fields."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        pct10 = [r for r in results if r.oversold in PCT_10_OVERSOLD and r.overbought in PCT_10_OVERBOUGHT]
        optimal = find_optimal_rsi_bands(sensitivity, pct10, results)
        for regime, o in optimal.items():
            assert "best_oversold" in o
            assert "best_overbought" in o
            assert "optimal_oversold_band" in o
            assert "optimal_overbought_band" in o
            assert "sensitivity_class" in o
            assert o["sensitivity_class"] in ("robust", "moderate", "sensitive")

    def test_sensitivity_classifications(self):
        """Should produce valid sensitivity classifications."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        pct10 = [r for r in results if r.oversold in PCT_10_OVERSOLD and r.overbought in PCT_10_OVERBOUGHT]
        optimal = find_optimal_rsi_bands(sensitivity, pct10, results)
        for regime, o in optimal.items():
            cv = o["sharpe_cv"]
            if cv < 0.15:
                assert o["sensitivity_class"] == "robust"
            elif cv < 0.30:
                assert o["sensitivity_class"] == "moderate"
            else:
                assert o["sensitivity_class"] == "sensitive"


class TestProfitFactor:
    """Tests for profit factor calculation."""

    def test_profit_factor_basic(self):
        """Basic profit factor calculation."""
        pnl = [10.0, -5.0, 15.0, -10.0]
        pf = calculate_profit_factor_from_pnl(pnl)
        assert pf == (25.0 / 15.0)  # gross_profit / gross_loss

    def test_profit_factor_no_losses(self):
        """Profit factor should be inf when no losses."""
        pnl = [10.0, 5.0, 15.0]
        pf = calculate_profit_factor_from_pnl(pnl)
        assert math.isinf(pf) and pf > 0

    def test_profit_factor_all_losses(self):
        """Profit factor should be 0 when all losses."""
        pnl = [-10.0, -5.0, -15.0]
        pf = calculate_profit_factor_from_pnl(pnl)
        assert pf == 0.0

    def test_profit_factor_empty(self):
        """Profit factor should be 0 for empty list."""
        pf = calculate_profit_factor_from_pnl([])
        assert pf == 0.0


class TestSaveResults:
    """Tests for result saving."""

    def test_save_results_creates_file(self, tmp_path):
        """save_results should create a JSON file."""
        results = [
            RSIResult(regime="bull", oversold=30.0, overbought=70.0, win_rate=0.5, sharpe_ratio=1.0),
        ]
        sensitivity = {"bull": RegimeSensitivity(
            regime="bull", best_oversold=30.0, best_overbought=70.0,
            best_sharpe=1.0, best_win_rate=0.5, best_max_dd=0.1,
            sharpe_range=0.1, win_rate_range=0.05, max_dd_range=0.05,
            sharpe_std=0.05, win_rate_std=0.02, max_dd_std=0.03,
            sharpe_cv=0.05,
        )}
        optimal = {"bull": {"best_oversold": 30.0, "best_overbought": 70.0}}

        output_path = str(tmp_path / "test_rsi.json")
        save_results(results, sensitivity, optimal, output_path)

        with open(output_path) as f:
            data = json.load(f)
        assert "metadata" in data
        assert "sensitivity" in data
        assert "all_results" in data
        assert "optimal_bands" in data


class TestIntegration:
    """Integration tests for the full analysis pipeline."""

    def test_full_pipeline(self):
        """Full pipeline should produce valid results."""
        candles = generate_synthetic_candles(n=720)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        pct10 = [r for r in results if r.oversold in PCT_10_OVERSOLD and r.overbought in PCT_10_OVERBOUGHT]
        optimal = find_optimal_rsi_bands(sensitivity, pct10, results)

        assert len(results) > 0
        assert len(sensitivity) > 0
        assert len(optimal) > 0
        assert "bull" in optimal

    def test_pipeline_with_more_data(self):
        """Pipeline should handle larger datasets."""
        candles = generate_synthetic_candles(n=1440)
        results = run_rsi_sweep(candles)
        sensitivity = analyze_sensitivity(results)
        pct10 = [r for r in results if r.oversold in PCT_10_OVERSOLD and r.overbought in PCT_10_OVERBOUGHT]
        optimal = find_optimal_rsi_bands(sensitivity, pct10, results)

        assert len(results) > 0
        assert len(sensitivity) > 0

    def test_results_consistency(self):
        """Results should be consistent across runs with same seed."""
        candles1 = generate_synthetic_candles(n=720, seed=42)
        candles2 = generate_synthetic_candles(n=720, seed=42)

        results1 = run_rsi_sweep(candles1)
        results2 = run_rsi_sweep(candles2)

        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1.regime == r2.regime
            assert r1.oversold == r2.oversold
            assert r1.overbought == r2.overbought
            assert abs(r1.win_rate - r2.win_rate) < 0.01
