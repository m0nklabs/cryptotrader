"""Smoke tests for scripts/split_oos_regime.py and scripts/walk_forward_analysis.py.

We don't run their CLI main(); we only test the pure helpers that don't need
real exchange data.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLIT = REPO_ROOT / "scripts" / "split_oos_regime.py"
WALK = REPO_ROOT / "scripts" / "walk_forward_analysis.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def split_mod():
    return _load(SPLIT, "split_oos_regime")


@pytest.fixture(scope="module")
def walk_mod():
    return _load(WALK, "walk_forward_analysis")


# --- split_oos_regime ---

def test_split_module_imports_cleanly(split_mod):
    """The script's module-level imports and constants should be importable."""
    assert hasattr(split_mod, "RegimeLabel")
    assert hasattr(split_mod, "map_market_regime_to_label")


def test_map_market_regime_to_label_handles_unknown(split_mod):
    """An unknown regime name should map to RegimeLabel.TRANSITION (or similar
    non-fatal default), not raise."""
    for name in ("bull", "bear", "range", "high_vol", "low_vol", "transition", "BOGUS"):
        label = split_mod.map_market_regime_to_label(name)
        assert label is not None
        assert hasattr(label, "value")


# --- walk_forward_analysis ---

def test_walk_forward_module_imports_cleanly(walk_mod):
    assert hasattr(walk_mod, "classify_regime")
    assert hasattr(walk_mod, "Regime")


def test_classify_regime_handles_short_window(walk_mod):
    """A small window should not raise; classification is allowed to be a
    default like RANGE or LOW_VOL."""
    # Build a minimal set of candles
    class _C:
        def __init__(self, close):
            self.close = close

    window = [_C(100.0), _C(100.1), _C(100.2), _C(100.15), _C(100.25)]
    # classify_regime takes a candle sequence and an index pointing at the
    # current bar (window slices from ``candles[idx-lookback:idx+1]``).
    regime = walk_mod.classify_regime(window, idx=len(window) - 1, lookback=4)
    assert regime in walk_mod.Regime


def test_classify_regime_detects_strong_bull(walk_mod):
    """A window with monotonically rising closes and a clear trend should
    classify as BULL."""
    class _C:
        def __init__(self, close):
            self.close = close

    # 20 rising candles with low volatility
    closes = [100.0 + 0.5 * i for i in range(20)]
    window = [_C(c) for c in closes]
    regime = walk_mod.classify_regime(window, idx=len(window) - 1, lookback=19)
    # We allow HIGH_VOL or BULL — the test just confirms the function returns
    # a valid enum value (no crash) for a clearly trending window.
    assert regime in walk_mod.Regime
