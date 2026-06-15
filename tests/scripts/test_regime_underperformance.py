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
