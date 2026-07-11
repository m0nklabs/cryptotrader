"""Smoke tests for the top-level validate_correlation.py script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "validate_correlation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_correlation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def test_run_validation_deterministic_with_seed(mod):
    """Same seed must produce identical correlation values."""
    a = mod.run_validation(count=80, threshold=0.7, seed=7)
    b = mod.run_validation(count=80, threshold=0.7, seed=7)
    assert a["matrix"].max_correlation == pytest.approx(
        b["matrix"].max_correlation, rel=1e-12
    )
    assert a["matrix"].min_correlation == pytest.approx(
        b["matrix"].min_correlation, rel=1e-12
    )


def test_run_validation_threshold_filters_pairs(mod):
    """A low threshold should flag more pairs than a high threshold."""
    loose = mod.run_validation(count=120, threshold=0.3, seed=11)
    strict = mod.run_validation(count=120, threshold=0.95, seed=11)
    assert len(strict["matrix"].overcorrelated_pairs) <= len(
        loose["matrix"].overcorrelated_pairs
    )
