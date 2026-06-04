"""Fake alpha rejection criteria.

Determines whether a strategy's apparent edge is genuine or
just luck (fake alpha) based on:
- Minimum trade count
- Cost-adjusted returns
- Statistical significance
- Regime diversity
- Consistency across metrics
"""

from __future__ import annotations

import math
from typing import Sequence

from core.strategy_eval.types import (
    RejectionCriteria,
    RejectionResult,
    RegimePerformance,
)


# ---------------------------------------------------------------------------
# Rejection logic
# ---------------------------------------------------------------------------


def evaluate_rejection(
    *,
    gross_return: float,
    total_costs: float,
    trades: Sequence,
    sharpe: float,
    win_rate: float,
    profit_factor: float,
    max_drawdown: float,
    regime_performance: list[RegimePerformance] | None = None,
    criteria: RejectionCriteria | None = None,
) -> RejectionResult:
    """Evaluate whether a strategy passes fake alpha rejection.

    Args:
        gross_return: Total gross return (before costs)
        total_costs: Total costs (fees + spread + slippage + latency)
        trades: Completed trades
        sharpe: Sharpe ratio
        win_rate: Win rate
        profit_factor: Profit factor
        max_drawdown: Maximum drawdown
        regime_performance: Per-regime performance data
        criteria: Rejection criteria

    Returns:
        RejectionResult with detailed analysis
    """
    if criteria is None:
        criteria = RejectionCriteria()

    net_return = gross_return - total_costs
    cost_ratio = total_costs / gross_return if abs(gross_return) > 1e-9 else 0.0

    reasons: list[str] = []
    rejected = False

    # Check minimum trades
    n_trades = len(trades)
    if n_trades < criteria.min_trades:
        reasons.append(
            f"Too few trades: {n_trades} < {criteria.min_trades} "
            f"(need {criteria.min_trades} for statistical significance)"
        )
        rejected = True

    # Check net return
    if net_return < criteria.min_net_return:
        reasons.append(f"Net return too low: {net_return:.2%} < " f"{criteria.min_net_return:.2%} minimum after costs")
        rejected = True

    # Check Sharpe
    if sharpe < criteria.min_sharpe:
        reasons.append(f"Sharpe ratio too low: {sharpe:.2f} < " f"{criteria.min_sharpe} minimum")
        rejected = True

    # Check win rate
    if win_rate < criteria.min_win_rate:
        reasons.append(f"Win rate too low: {win_rate:.2%} < " f"{criteria.min_win_rate} minimum")
        rejected = True

    # Check profit factor
    if profit_factor < criteria.min_profit_factor:
        reasons.append(f"Profit factor too low: {profit_factor:.2f} < " f"{criteria.min_profit_factor} minimum")
        rejected = True

    # Check drawdown
    if max_drawdown > criteria.max_drawdown_limit:
        reasons.append(f"Max drawdown too high: {max_drawdown:.2%} > " f"{criteria.max_drawdown_limit:.2%} limit")
        rejected = True

    # Check cost ratio
    if cost_ratio > 0.5:
        reasons.append(f"High cost ratio: {cost_ratio:.1%} of gross return consumed by costs")

    # Check regime diversity
    regime_diversity = 0
    if regime_performance:
        regime_diversity = sum(1 for r in regime_performance if r.n_trades >= criteria.min_trade_count_per_regime)
        if regime_diversity < 2:
            reasons.append(f"Limited regime diversity: only {regime_diversity} regimes " f"with sufficient trades")
            rejected = True

    # Statistical significance test
    if n_trades >= 2:
        is_significant, p_value = _statistical_significance(trades, criteria.significance_level)
    else:
        is_significant, p_value = False, 1.0

    if not is_significant:
        reasons.append(f"Not statistically significant: p={p_value:.3f} >= " f"{criteria.significance_level}")
        rejected = True

    return RejectionResult(
        rejected=rejected,
        reasons=tuple(reasons),
        net_return=net_return,
        gross_return=gross_return,
        total_costs=total_costs,
        cost_ratio=cost_ratio,
        sharpe=sharpe,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        trade_count=n_trades,
        regime_diversity=regime_diversity,
        is_significant=is_significant,
        p_value=p_value,
    )


def is_fake_alpha(result: RejectionResult) -> bool:
    """Quick check: is this strategy's alpha fake?

    Args:
        result: RejectionResult from evaluate_rejection

    Returns:
        True if alpha is likely fake (rejected)
    """
    return result.rejected


def _statistical_significance(
    trades: Sequence,
    significance_level: float = 0.05,
) -> tuple[bool, float]:
    """Test if trade returns are statistically significant.

    Uses a t-test against zero return.

    Args:
        trades: Sequence of trades with pnl attribute
        significance_level: P-value threshold

    Returns:
        (is_significant, p_value)
    """
    pnls = [float(t.pnl) if hasattr(t, "pnl") else 0.0 for t in trades]
    n = len(pnls)

    if n < 2:
        return False, 1.0

    mean_pnl = sum(pnls) / n
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / (n - 1)
    std_err = math.sqrt(variance / n) if variance > 0 else 0.0

    if std_err == 0:
        return mean_pnl > 0, 0.0

    # t-statistic
    t_stat = mean_pnl / std_err

    # Approximate p-value using normal distribution
    p_value = 2 * (1 - _normal_cdf(abs(t_stat)))

    return p_value < significance_level, p_value


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Cost-adjusted evaluation
# ---------------------------------------------------------------------------


def evaluate_with_costs(
    *,
    gross_return: float,
    fee_rate: float,
    spread_bps: int,
    slippage_bps: int,
    latency_cost_per_trade: float,
    n_trades: int,
    notional_per_trade: float,
) -> RejectionResult:
    """Evaluate strategy with explicit cost breakdown.

    Args:
        gross_return: Gross return before costs
        fee_rate: Fee rate (e.g., 0.001 = 0.1%)
        spread_bps: Spread in basis points
        slippage_bps: Slippage in basis points
        latency_cost_per_trade: Fixed latency cost per trade
        n_trades: Number of trades
        notional_per_trade: Average notional per trade

    Returns:
        RejectionResult with cost-adjusted metrics
    """
    # Calculate total costs
    total_fees = n_trades * notional_per_trade * fee_rate
    spread_cost = n_trades * notional_per_trade * spread_bps / 10000
    slippage_cost = n_trades * notional_per_trade * slippage_bps / 10000
    latency_total = n_trades * latency_cost_per_trade
    total_costs = total_fees + spread_cost + slippage_cost + latency_total

    return RejectionResult(
        rejected=False,  # Will be set by caller
        reasons=("Costs evaluated",),
        net_return=gross_return - total_costs,
        gross_return=gross_return,
        total_costs=total_costs,
        cost_ratio=total_costs / gross_return if abs(gross_return) > 1e-9 else 0.0,
        sharpe=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        max_drawdown=0.0,
        trade_count=n_trades,
        regime_diversity=0,
        is_significant=True,
        p_value=0.0,
    )
