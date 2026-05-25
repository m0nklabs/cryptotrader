"""Overfitting detection and parameter stability analysis.

Detects overfitting by:
1. Sweeping parameters around their optimal values
2. Applying multiple testing correction (Bonferroni)
3. Computing parameter stability metrics
4. Assessing overall overfitting risk
"""

from __future__ import annotations

import math
from typing import Any, Callable

from core.strategy_eval.types import OverfittingCheck, ParameterSweep


# ---------------------------------------------------------------------------
# Parameter sweep
# ---------------------------------------------------------------------------


def sweep_parameter(
    *,
    param_name: str,
    param_values: list[Any],
    evaluate_fn: Callable[[Any], float],
    optimal_value: Any,
    optimal_return: float,
) -> ParameterSweep:
    """Sweep a parameter around its optimal value.

    Args:
        param_name: Parameter name
        param_values: List of values to test
        evaluate_fn: Function that takes a parameter value and returns return
        optimal_value: The best-found parameter value
        optimal_return: Return at the optimal value

    Returns:
        ParameterSweep with stability metrics
    """
    returns = [evaluate_fn(v) for v in param_values]
    best_idx = max(range(len(returns)), key=lambda i: returns[i])
    best_value = param_values[best_idx]
    best_return = returns[best_idx]

    return_range = max(returns) - min(returns)
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    std_dev = math.sqrt(variance)

    # Stable if the return range is less than 2x the standard deviation
    is_stable = return_range < 2 * std_dev if std_dev > 0 else True

    return ParameterSweep(
        param_name=param_name,
        param_values=param_values,
        returns=returns,
        best_value=best_value,
        best_return=best_return,
        return_range=return_range,
        std_dev=std_dev,
        is_stable=is_stable,
    )


def compute_parameter_stability(
    *,
    strategy_class: type,
    base_params: dict[str, Any],
    param_ranges: dict[str, list[Any]],
    evaluate_fn: Callable[[dict[str, Any]], float],
) -> list[ParameterSweep]:
    """Compute parameter stability for all parameters.

    Sweeps each parameter individually while holding others constant.

    Args:
        strategy_class: Strategy class to instantiate
        base_params: Base parameter values
        param_ranges: Dict of param_name -> list of values to sweep
        evaluate_fn: Function that takes params dict and returns return

    Returns:
        List of ParameterSweep for each parameter
    """
    sweeps = []

    for param_name, values in param_ranges.items():

        def make_eval(pn, base):
            def evaluate(value):
                params = base.copy()
                params[pn] = value
                return evaluate_fn(params)

            return evaluate

        # Find optimal value
        opt_value = max(values, key=make_eval(param_name, base_params))
        opt_return = evaluate_fn({**base_params, param_name: opt_value})

        sweep = sweep_parameter(
            param_name=param_name,
            param_values=values,
            evaluate_fn=make_eval(param_name, base_params),
            optimal_value=opt_value,
            optimal_return=opt_return,
        )
        sweeps.append(sweep)

    return sweeps


# ---------------------------------------------------------------------------
# Overfitting detection
# ---------------------------------------------------------------------------


def check_overfitting(
    *,
    in_sample_return: float,
    out_of_sample_return: float,
    n_parameters: int,
    n_tests: int = 1,
    param_sweeps: list[ParameterSweep] | None = None,
) -> OverfittingCheck:
    """Check for overfitting between in-sample and out-of-sample performance.

    Args:
        in_sample_return: Return on training data
        out_of_sample_return: Return on test data
        n_parameters: Number of tuned parameters
        n_tests: Number of strategy tests performed
        param_sweeps: Optional parameter sweep results

    Returns:
        OverfittingCheck with detailed results
    """
    # OOS/IS ratio
    if abs(in_sample_return) > 1e-9:
        oos_is_ratio = out_of_sample_return / in_sample_return
    else:
        oos_is_ratio = 0.0

    # Bonferroni correction
    bonferroni_threshold = 0.05 / n_tests if n_tests > 0 else 0.05
    multiple_testing_corrected = bonferroni_threshold < 0.05

    # Parameter stability
    stable_count = 0
    if param_sweeps:
        stable_count = sum(1 for s in param_sweeps if s.is_stable)
    param_stability_ratio = stable_count / len(param_sweeps) if param_sweeps else 1.0

    # Overfit score (0 = no overfit, 1 = severe)
    # Factors: OOS/IS decay, parameter stability, multiple testing
    decay_penalty = max(0, 1 - oos_is_ratio) if oos_is_ratio > 0 else 0.5
    stability_penalty = 1 - param_stability_ratio
    test_penalty = min(1, n_tests / 10)  # penalize > 10 tests

    overfit_score = 0.4 * decay_penalty + 0.3 * stability_penalty + 0.3 * test_penalty
    is_overfitted = overfit_score > 0.5

    return OverfittingCheck(
        parameter_stability=param_sweeps or [],
        multiple_testing_corrected=multiple_testing_corrected,
        bonferroni_threshold=bonferroni_threshold,
        effective_tests=n_tests,
        is_overfitted=is_overfitted,
        overfit_score=overfit_score,
    )


# ---------------------------------------------------------------------------
# Lighthouse test (anti-data-snooping)
# ---------------------------------------------------------------------------


def lighthouse_test(
    *,
    returns: list[float],
    n_shuffles: int = 100,
    significance_level: float = 0.05,
) -> dict[str, float]:
    """Lighthouse test for fake alpha detection.

    Shuffles returns to create null distribution and checks
    if observed performance is significantly better than random.

    Args:
        returns: List of strategy returns
        n_shuffles: Number of shuffle iterations
        significance_level: P-value threshold

    Returns:
        Dictionary with test results
    """
    if not returns:
        return {
            "observed_mean": 0.0,
            "null_mean": 0.0,
            "p_value": 1.0,
            "is_significant": False,
            "alpha": 0.0,
        }

    observed_mean = sum(returns) / len(returns)

    # Create null distribution by shuffling
    import random

    random.seed(42)
    null_means = []
    for _ in range(n_shuffles):
        shuffled = returns.copy()
        random.shuffle(shuffled)
        null_means.append(sum(shuffled) / len(shuffled))

    null_mean = sum(null_means) / len(null_means)
    null_std = (
        math.sqrt(sum((m - null_mean) ** 2 for m in null_means) / (len(null_means) - 1)) if len(null_means) > 1 else 0.0
    )

    # P-value: fraction of null means >= observed
    p_value = sum(1 for m in null_means if m >= observed_mean) / n_shuffles

    # Alpha = observed - expected (null mean)
    alpha = observed_mean - null_mean

    return {
        "observed_mean": observed_mean,
        "null_mean": null_mean,
        "null_std": null_std,
        "p_value": p_value,
        "is_significant": p_value < significance_level,
        "alpha": alpha,
    }
