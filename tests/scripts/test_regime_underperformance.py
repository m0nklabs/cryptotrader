"""Smoke + key behavioural tests for scripts/regime_underperformance_analysis.py.

These tests focus on the data-driven path: ``estimate_regime_metrics`` must
use the OOS per-segment statistics, not hand-coded multipliers.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "regime_underperformance_analysis.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "regime_underperformance_analysis", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def _make_oos(segments):
    return {"metadata": {"total_candles": sum(s["n_candles"] for s in segments)}, "segments": segments}


def _backtest():
    return {
        "metrics": {
            "sharpe_ratio": 0.46,
            "max_drawdown": 0.35,
            "win_rate": 0.6,
            "profit_factor": 1.5,
            "total_return": 0.25,
        }
    }


def test_estimate_regime_metrics_uses_oos_data_not_handcoded(mod):
    """The per-regime mean_return must reflect the OOS segment's mean_return,
    not the hand-coded regime_multipliers dict that the prior version used."""
    oos = _make_oos(
        [
            {
                "name": "train",
                "n_candles": 1000,
                "regime_breakdown": {"bull": 60.0, "bear": 40.0},
                "mean_return": 0.0002,  # 2e-4 per candle
                "mean_volatility": 0.02,
            }
        ]
    )
    metrics = mod.estimate_regime_metrics(oos, _backtest())

    assert "bull" in metrics
    assert "bear" in metrics
    # Both regimes share the same single-segment mean_return, so they should
    # come out equal (≈ 0.0002), not the 1.3/0.6 multipliers of the old code.
    assert metrics["bull"].mean_return == pytest.approx(0.0002, rel=1e-9)
    assert metrics["bear"].mean_return == pytest.approx(0.0002, rel=1e-9)
    # Bull and bear should NOT be 1.3x and 0.6x of each other.
    assert metrics["bull"].mean_return != pytest.approx(
        1.3 * metrics["bear"].mean_return, rel=1e-3
    )


def test_estimate_regime_metrics_handles_empty_oos(mod, capsys):
    """Empty OOS data should emit a warning and return an empty dict."""
    metrics = mod.estimate_regime_metrics({"segments": []}, _backtest())
    assert metrics == {}
    captured = capsys.readouterr()
    assert "no per-regime candle counts" in captured.err


def test_estimate_regime_metrics_warns_on_missing_backtest_fields(mod, capsys):
    """Missing backtest fields should produce a stderr warning, not silently
    fall back to zero metrics."""
    metrics = mod.estimate_regime_metrics(
        _make_oos(
            [
                {
                    "name": "train",
                    "n_candles": 100,
                    "regime_breakdown": {"bull": 100.0},
                    "mean_return": 0.0001,
                    "mean_volatility": 0.02,
                }
            ]
        ),
        {"metrics": {}},
    )
    captured = capsys.readouterr()
    assert "missing one of" in captured.err
    # max_drawdown/win_rate/profit_factor all default to 0.0
    assert metrics["bull"].max_drawdown == 0.0
    assert metrics["bull"].win_rate == 0.0
    assert metrics["bull"].profit_factor == 0.0


def test_per_regime_sharpe_is_data_driven(mod):
    """Per-regime Sharpe is computed as mean_return/mean_volatility * sqrt(8760)."""
    oos = _make_oos(
        [
            {
                "name": "train",
                "n_candles": 1000,
                "regime_breakdown": {"bull": 100.0},
                "mean_return": 0.001,
                "mean_volatility": 0.02,
            }
        ]
    )
    metrics = mod.estimate_regime_metrics(oos, _backtest())
    expected = (0.001 / 0.02) * (8760 ** 0.5)
    assert metrics["bull"].sharpe_ratio == pytest.approx(expected, rel=1e-9)


def test_full_report_against_repo_artifacts(mod):
    """End-to-end run against the JSON artifacts checked into the repo must
    produce a report with non-empty per-regime metrics and a comparison dict."""
    oos = json.loads((REPO_ROOT / "oos_regime_dataset.json").read_text())
    bt = json.loads((REPO_ROOT / "backtest_results.json").read_text())
    metrics = mod.estimate_regime_metrics(oos, bt)
    assert "bull" in metrics
    assert "bear" in metrics
    assert "range" in metrics
    # Each metric should be a RegimeMetrics instance with positive candle count
    for m in metrics.values():
        assert m.n_candles > 0
        assert m.mean_volatility > 0


def test_generate_report_bear_acceptable_for_live_uses_live_thresholds(mod):
    """`bear_acceptable['acceptable_for_live']` must be the live-threshold
    result, not a copy of the paper-threshold result. Regression test for
    the post-rebase bug where both labels read the same dict key."""
    oos = _make_oos(
        [
            {
                "name": "train",
                "n_candles": 1200,  # 1 trade per 100 candles → 12 trades
                "regime_breakdown": {"bear": 100.0},
                "mean_return": 0.0002,
                "mean_volatility": 0.02,
            }
        ]
    )
    # Use a backtest that passes all the metric thresholds for paper. The
    # only difference between paper and live here is the n_trades floor
    # (10 vs 15); with 12 trades the regime passes paper and fails live.
    bt = {
        "metrics": {
            "sharpe_ratio": 1.0,
            "max_drawdown": 0.10,
            "win_rate": 0.60,
            "profit_factor": 1.5,
            "total_return": 0.5,
        }
    }
    report = mod.generate_report(oos, bt)
    assert report.bear_acceptable.get("all_ok") is True, (
        "bear must be paper-acceptable for the per-regime candle count to "
        "matter; the regression is in the live label"
    )
    # The live check is keyed separately; it must be False because 12
    # trades < LIVE_THRESHOLDS.min_trades (15).
    assert report.bear_acceptable.get("acceptable_for_live") is False


def test_generate_report_range_acceptable_for_live_uses_live_thresholds(mod):
    """Same regression for range: paper-acceptable, but live must fail."""
    oos = _make_oos(
        [
            {
                "name": "train",
                "n_candles": 1200,  # 1 trade per 100 candles → 12 trades
                "regime_breakdown": {"range": 100.0},
                "mean_return": 0.0002,
                "mean_volatility": 0.02,
            }
        ]
    )
    bt = {
        "metrics": {
            "sharpe_ratio": 1.0,
            "max_drawdown": 0.10,
            "win_rate": 0.60,
            "profit_factor": 1.5,
            "total_return": 0.5,
        }
    }
    report = mod.generate_report(oos, bt)
    assert report.range_acceptable.get("all_ok") is True
    assert report.range_acceptable.get("acceptable_for_live") is False


def test_print_report_no_double_plus_format(mod, capsys):
    """Regression for the 'DD ++0.0%' formatting bug. The label
    'DD +' plus a `:+.1%` format spec produced '++0.0%' when the value was
    exactly 0.0 (the common case once we fall back to the overall backtest
    as a DD/WR/PF proxy)."""
    oos = _make_oos(
        [
            {
                "name": "train",
                "n_candles": 1000,
                "regime_breakdown": {"bear": 50.0, "transition": 50.0},
                "mean_return": 0.0,
                "mean_volatility": 0.02,
            }
        ]
    )
    bt = {
        "metrics": {
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_return": 0.0,
        }
    }
    report = mod.generate_report(oos, bt)
    mod.print_report(report)
    captured = capsys.readouterr()
    assert "++" not in captured.out, (
        "Found a '++' substring in print_report output; the label/format "
        "fix has regressed:\n" + captured.out
    )


def test_report_to_dict_bear_acceptable_for_live_key(mod):
    """`report_to_dict` must emit a distinct `acceptable_for_live` value for
    bear / range, computed against LIVE_THRESHOLDS, not duplicated from
    the paper value."""
    oos = json.loads((REPO_ROOT / "oos_regime_dataset.json").read_text())
    bt = json.loads((REPO_ROOT / "backtest_results.json").read_text())
    report = mod.generate_report(oos, bt)
    out = mod.report_to_dict(report)
    # Both keys exist and are bool
    assert "acceptable_for_paper" in out["bear_vs_transition"]
    assert "acceptable_for_live" in out["bear_vs_transition"]
    assert isinstance(out["bear_vs_transition"]["acceptable_for_live"], bool)
    assert isinstance(out["bear_vs_transition"]["acceptable_for_paper"], bool)
    # And the same for range
    assert "acceptable_for_live" in out["range_vs_transition"]
    assert isinstance(out["range_vs_transition"]["acceptable_for_live"], bool)
