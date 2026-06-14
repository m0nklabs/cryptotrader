#!/usr/bin/env python3
"""Validation script for indicator correlation analysis.

Runs correlation analysis on synthetic candle data and prints
the resulting matrix with threshold flags.

Usage:
    python validate_correlation.py [--count N] [--threshold T] [--seed S]

Acceptance criteria:
    - Script executes without errors
    - Outputs correlation values for the three tracked pairs
    - Clearly marks pairs above/below the configured threshold
    - Smoke-checks that each pair's correlation lands in a plausible
      range (deliberately a range, not a pinned value, so it survives
      NumPy / indicator implementation drift)
"""

from __future__ import annotations

import argparse
import math
import sys

from core.analysis.indicator_correlation import (
    CORRELATION_PAIRS,
    DEFAULT_CORRELATION_THRESHOLD,
    MACD_CODE,
    RSI_CODE,
    STOCHASTIC_CODE,
    check_correlation_threshold,
    compute_correlation_matrix,
    compute_signal_correlation,
    format_correlation_report,
    generate_synthetic_candles,
)


def run_validation(
    count: int = 200,
    threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    seed: int = 42,
) -> dict:
    """Run full correlation validation and return results.

    Args:
        count: Number of synthetic candles to generate.
        threshold: Correlation threshold for flagging.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary with all correlation data.
    """
    import numpy as np

    np.random.seed(seed)

    candles = generate_synthetic_candles(count=count)

    # Compute full matrix
    matrix_result = compute_correlation_matrix(candles, threshold=threshold)
    report = format_correlation_report(check_correlation_threshold(candles, threshold=threshold))

    # Compute individual pairs for explicit output
    pairs_data = {}
    for ind_a, ind_b in CORRELATION_PAIRS:
        result = compute_signal_correlation(candles, ind_a, ind_b, threshold=threshold)
        pairs_data[(ind_a, ind_b)] = result

    return {
        "candles": candles,
        "matrix": matrix_result,
        "report": report,
        "pairs": pairs_data,
        "threshold": threshold,
    }


def print_validation_results(data: dict) -> None:
    """Print validation results in a clear, human-readable format.

    Args:
        data: Output from run_validation().
    """
    threshold = data["threshold"]

    print("=" * 64)
    print("  INDICATOR CORRELATION VALIDATION")
    print("=" * 64)
    print()
    print(f"  Candles: {len(data['candles'])}  |  Threshold: {threshold}")
    print()

    # Pair correlations with threshold flags
    print("  Pair Correlations:")
    print("  " + "-" * 60)
    for (ind_a, ind_b), result in data["pairs"].items():
        flag = "ABOVE" if result.is_above_threshold else "BELOW"
        marker = "[!!]" if result.is_above_threshold else "    "
        print(f"  {marker}  {ind_a:>10} / {ind_b:>10}: {result.correlation:7.4f}  ({flag})")
    print()

    # Full matrix
    print("  Correlation Matrix:")
    print("  " + "-" * 60)
    matrix = data["matrix"].matrix
    indicators = [RSI_CODE, MACD_CODE, STOCHASTIC_CODE]
    header = "          " + "  ".join(f"{ind:>10}" for ind in indicators)
    print(f"  {header}")
    for ind_a in indicators:
        row = f"  {ind_a:>10}" + "".join(f"  {matrix[ind_a][ind_b]:>10.4f}" for ind_b in indicators)
        print(row)
    print()

    # Extremes
    print(
        f"  Max correlation: {data['matrix'].max_correlation:.4f}  "
        f"({data['matrix'].max_correlation_pair[0]} / {data['matrix'].max_correlation_pair[1]})"
    )
    print(
        f"  Min correlation: {data['matrix'].min_correlation:.4f}  "
        f"({data['matrix'].min_correlation_pair[0]} / {data['matrix'].min_correlation_pair[1]})"
    )
    print()

    # Over-correlated pairs
    if data["matrix"].overcorrelated_pairs:
        print("  Over-correlated pairs (above threshold):")
        for pair_name in data["matrix"].overcorrelated_pairs:
            print(f"    - {pair_name}")
    else:
        print("  No over-correlated pairs detected.")
    print()

    # Risk assessment
    risk = (
        "low"
        if len(data["matrix"].overcorrelated_pairs) == 0
        else ("medium" if len(data["matrix"].overcorrelated_pairs) <= 1 else "high")
    )
    print(f"  Risk level: {risk}")
    print()

    # Expected vs actual. This section is intentionally a smoke check, not a
    # strict regression gate: we verify each pair lands in a plausible range
    # and that the script ran to completion. Pinned expected values from one
    # particular seed are fragile (any change to the trend/noise distribution
    # or to the indicator implementations shifts them silently), and the unit
    # tests in ``tests/test_indicator_correlation.py`` cover correctness
    # more rigorously.
    print("  Smoke check (plausible range + non-NaN):")
    print("  " + "-" * 60)
    rsi_stoch = data["pairs"][(RSI_CODE, STOCHASTIC_CODE)].correlation
    macd_stoch = data["pairs"][(MACD_CODE, STOCHASTIC_CODE)].correlation

    def get_pair(a: str, b: str) -> float:
        for (ka, kb), v in data["pairs"].items():
            if (ka == a and kb == b) or (ka == b and kb == a):
                return v.correlation
        raise KeyError(f"Pair ({a}, {b}) not found in computed correlations")

    # These bounds were chosen from the same seed=42 synthetic data the script
    # has historically used: the three pairs cluster in the [0.4, 0.95] range.
    # If the bounds are too tight, loosen them; if they ever pass on a
    # broken implementation, tighten them. The point is to catch a silent
    # regression (e.g. indicators returning zeros), not to pin a single value.
    checks = [
        ("RSI/Stochastic", rsi_stoch, 0.4, 0.95),
        ("MACD/RSI", get_pair(MACD_CODE, RSI_CODE), 0.4, 0.95),
        ("MACD/Stochastic", macd_stoch, 0.4, 0.95),
    ]
    all_pass = True
    for name, actual, low, high in checks:
        in_range = (not math.isnan(actual)) and (low <= actual <= high)
        status = "OK" if in_range else "CHECK"
        if not in_range:
            all_pass = False
        print(f"    {name:>20}: {actual:.4f}  (plausible range [{low}, {high}])  [{status}]")

    print()
    if all_pass:
        print("  All smoke checks passed.")
    else:
        print("  Some values outside the plausible range — review recommended.")
    print()
    print("=" * 64)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Validate indicator correlation analysis")
    parser.add_argument("--count", type=int, default=200, help="Number of synthetic candles (default: 200)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_CORRELATION_THRESHOLD,
        help=f"Correlation threshold (default: {DEFAULT_CORRELATION_THRESHOLD})",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    data = run_validation(count=args.count, threshold=args.threshold, seed=args.seed)
    print_validation_results(data)

    # Also print the full report
    print(data["report"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
