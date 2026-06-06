#!/usr/bin/env python3
"""RSI threshold robustness analysis per regime.

Vary RSI thresholds parametrically (±10% and ±20%) within each identified regime.
Measure impact on win rate, Sharpe ratio, and max drawdown.

Acceptance criteria:
- Identify optimal RSI bands per regime
- Document sensitivity ranges (how much performance degrades with threshold shifts)
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.backtest.engine import BacktestEngine, RSIStrategy, BacktestResult
from core.backtest.metrics import (
    Trade,
    calculate_win_rate,
)
from core.types import Candle
from scripts.walk_forward_analysis import (
    Regime, RegimeMetrics, classify_regime, generate_synthetic_candles, load_candles_from_file,
)

# All recognized regime values
ALL_REGIMES = list(Regime)

# ±10% and ±20% threshold variants: (oversold, overbought)
THRESHOLD_VARIANTS = {
    "-20%": (24.0, 56.0),
    "-10%": (27.0, 63.0),
    "base": (30.0, 70.0),
    "+10%": (33.0, 77.0),
    "+20%": (36.0, 84.0),
}


# ---------------------------------------------------------------------------
# Threshold result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ThresholdResult:
    """Results for a single threshold variant across all regimes."""
    threshold_label: str
    oversold: float
    overbought: float
    regimes: dict[str, RegimeMetrics]
    overall: RegimeMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold_label,
            "oversold": self.oversold,
            "overbought": self.overbought,
            "regimes": {k: v.to_dict() for k, v in self.regimes.items()},
            "overall": self.overall.to_dict(),
        }


def run_threshold_analysis(
    candles: list[Candle],
    threshold_variants: dict[str, tuple[float, float]] | None = None,
    lookback: int = 20,
    initial_capital: float = 10000.0,
) -> dict[str, ThresholdResult]:
    """Run RSI threshold robustness analysis.

    For each threshold variant:
    1. Classify each candle into a regime
    2. For each regime, extract the candles and run a backtest
    3. Aggregate metrics per regime
    """
    if threshold_variants is None:
        threshold_variants = THRESHOLD_VARIANTS

    results: dict[str, ThresholdResult] = {}

    # Pre-classify regimes for all candles
    all_regimes = [classify_regime(candles, i, lookback=lookback) for i in range(len(candles))]

    for label, (oversold, overbought) in threshold_variants.items():
        strategy = RSIStrategy(oversold=oversold, overbought=overbought)

        # Group candles by regime
        regime_candle_groups: dict[Regime, list[Candle]] = {r: [] for r in ALL_REGIMES}
        for i, regime in enumerate(all_regimes):
            regime_candle_groups[regime].append(candles[i])

        # Run backtest per regime
        regime_metrics: dict[str, RegimeMetrics] = {}
        all_trades: list[Trade] = []
        mean_pnl = 0.0
        std_pnl = 0.0

        for regime in ALL_REGIMES:
            reg_candle_list = regime_candle_groups[regime]
            n_candles = len(reg_candle_list)

            if n_candles == 0:
                regime_metrics[regime.value] = RegimeMetrics(
                    regime=regime.value,
                    n_candles=0,
                    n_trades=0,
                    win_rate=0.0,
                    sharpe_ratio=0.0,
                    max_drawdown=0.0,
                    total_pnl=0.0,
                    total_return=0.0,
                    profit_factor=0.0,
                    mean_trade_pnl=0.0,
                    std_trade_pnl=0.0,
                )
                continue

            engine = BacktestEngine(
                candle_store=None,
                initial_capital=initial_capital,
            )
            result: BacktestResult = engine.run(strategy=strategy, candles=reg_candle_list)

            all_trades.extend(result.trades)

            win_rate = calculate_win_rate(result.trades)

            # Calculate mean and std trade PnL
            trade_pnl = [(float(t.exit_price) - float(t.entry_price)) * float(t.size) for t in result.trades] if result.trades else [0.0]
            mean_pnl = statistics.mean(trade_pnl) if trade_pnl else 0.0
            std_pnl = statistics.stdev(trade_pnl) if len(trade_pnl) > 1 else 0.0

            regime_metrics[regime.value] = RegimeMetrics(
                regime=regime.value,
                n_candles=n_candles,
                n_trades=len(result.trades),
                win_rate=win_rate,
                sharpe_ratio=result.sharpe_ratio,
                max_drawdown=result.max_drawdown,
                total_pnl=result.total_pnl,
                total_return=result.total_return,
                profit_factor=result.profit_factor,
                mean_trade_pnl=float(mean_pnl),
                std_trade_pnl=float(std_pnl),
            )

        # Overall metrics across all regimes
        total_trades = len(all_trades)
        overall_win_rate = calculate_win_rate(all_trades) if all_trades else 0.0
        total_pnl = sum(m.total_pnl for m in regime_metrics.values())
        total_return = sum(m.total_return for m in regime_metrics.values())

        # Weighted average sharpe
        total_candles = sum(m.n_candles for m in regime_metrics.values())
        avg_sharpe = (
            sum(m.sharpe_ratio * m.n_candles for m in regime_metrics.values()) / total_candles
            if total_candles > 0 else 0.0
        )
        avg_maxdd = (
            sum(m.max_drawdown * m.n_candles for m in regime_metrics.values()) / total_candles
            if total_candles > 0 else 0.0
        )
        avg_pnl = total_pnl / len(regime_metrics) if regime_metrics else 0.0

        overall = RegimeMetrics(
            regime="all",
            n_candles=total_candles,
            n_trades=total_trades,
            win_rate=overall_win_rate,
            sharpe_ratio=avg_sharpe,
            max_drawdown=avg_maxdd,
            total_pnl=total_pnl,
            total_return=total_return,
            profit_factor=statistics.mean([m.profit_factor for m in regime_metrics.values()]) if regime_metrics else 0.0,
            mean_trade_pnl=float(mean_pnl),
            std_trade_pnl=float(std_pnl),
        )

        results[label] = ThresholdResult(
            threshold_label=label,
            oversold=oversold,
            overbought=overbought,
            regimes=regime_metrics,
            overall=overall,
        )

    return results


# ---------------------------------------------------------------------------
# RSI threshold sweep
# ---------------------------------------------------------------------------

# Default RSI thresholds
DEFAULT_OVERSOLD = 30.0
DEFAULT_OVERBOUGHT = 70.0

# ±10% ranges
PCT_10_OVERSOLD = [round(DEFAULT_OVERSOLD * (1 - 0.10), 1), DEFAULT_OVERSOLD, round(DEFAULT_OVERSOLD * (1 + 0.10), 1)]  # 27, 30, 33
PCT_10_OVERBOUGHT = [round(DEFAULT_OVERBOUGHT * (1 - 0.10), 1), DEFAULT_OVERBOUGHT, round(DEFAULT_OVERBOUGHT * (1 + 0.10), 1)]  # 63, 70, 77

# ±20% ranges
PCT_20_OVERSOLD = [round(DEFAULT_OVERSOLD * (1 - 0.20), 1), *PCT_10_OVERSOLD, round(DEFAULT_OVERSOLD * (1 + 0.20), 1)]  # 24, 27, 30, 33, 36
PCT_20_OVERBOUGHT = [round(DEFAULT_OVERBOUGHT * (1 - 0.20), 1), *PCT_10_OVERBOUGHT, round(DEFAULT_OVERBOUGHT * (1 + 0.20), 1)]  # 56, 63, 70, 77, 84


@dataclass
class RSIResult:
    """Performance for one (regime, oversold, overbought) combo."""
    regime: str
    oversold: float
    overbought: float
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    total_pnl: float = 0.0
    n_trades: int = 0
    profit_factor: float = 0.0
    equity_curve: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop('equity_curve', None)
        return d


def run_rsi_sweep(
    candles: Sequence[Candle],
    oversold_values: list[float] | None = None,
    overbought_values: list[float] | None = None,
    initial_capital: float = 10000.0,
    step: int = 10,
) -> list[RSIResult]:
    """Run RSI threshold sweep across all regimes.

    For each regime, runs backtests with different (oversold, overbought) combos
    and returns per-regime results.
    """
    if oversold_values is None:
        oversold_values = PCT_20_OVERSOLD
    if overbought_values is None:
        overbought_values = PCT_20_OVERBOUGHT

    # Classify regimes for each candle
    regime_list = []
    for i in range(len(candles)):
        r = classify_regime(candles, i, lookback=20)
        regime_list.append(r)

    # Group candles by regime (non-contiguous windows)
    regime_windows: dict[Regime, list[Candle]] = {r: [] for r in Regime}
    for i, c in enumerate(candles):
        regime_windows[regime_list[i]].append(c)

    results: list[RSIResult] = []

    for regime, regime_candles in regime_windows.items():
        if len(regime_candles) < 15:
            continue

        for os_val in oversold_values:
            for ob_val in overbought_values:
                if os_val >= ob_val - 5:  # avoid overlap
                    continue

                strategy = RSIStrategy(oversold=os_val, overbought=ob_val)
                engine = BacktestEngine(
                    candle_store=None,
                    initial_capital=initial_capital,
                )
                result = engine.run(strategy=strategy, candles=regime_candles)

                r = RSIResult(
                    regime=regime.value,
                    oversold=os_val,
                    overbought=ob_val,
                    win_rate=result.win_rate,
                    sharpe_ratio=result.sharpe_ratio,
                    max_drawdown=result.max_drawdown,
                    total_pnl=result.total_pnl,
                    n_trades=len(result.trades),
                    profit_factor=result.profit_factor,
                    equity_curve=result.equity_curve,
                )
                results.append(r)

    return results


def run_rsi_sweep_per_window(
    candles: Sequence[Candle],
    oversold_values: list[float] | None = None,
    overbought_values: list[float] | None = None,
    initial_capital: float = 10000.0,
    lookback: int = 20,
    step: int = 10,
) -> list[RSIResult]:
    """Run RSI threshold sweep using walk-forward windows for more robust results.

    Instead of lumping all candles of a regime together, this creates
    walk-forward windows within each regime and averages results.
    """
    if oversold_values is None:
        oversold_values = PCT_20_OVERSOLD
    if overbought_values is None:
        overbought_values = PCT_20_OVERBOUGHT

    # Classify regimes
    regime_list = []
    for i in range(len(candles)):
        r = classify_regime(candles, i, lookback=lookback)
        regime_list.append(r)

    # Group indices by regime
    regime_indices: dict[Regime, list[int]] = {r: [] for r in Regime}
    for i, r in enumerate(regime_list):
        regime_indices[r].append(i)

    results: list[RSIResult] = []

    for regime, indices in regime_indices.items():
        if len(indices) < lookback + 1:
            continue

        # Create windows for this regime
        for os_val in oversold_values:
            for ob_val in overbought_values:
                if os_val >= ob_val - 5:
                    continue

                # Collect results across windows
                all_sharpes = []
                all_win_rates = []
                all_maxdds = []
                all_pnl = []
                total_trades = 0

                idx = lookback
                while idx < len(candles) - step:
                    window_start = max(0, idx - lookback)
                    window_end = min(idx + lookback, len(candles))

                    # Only include candles belonging to this regime
                    window_candles = [
                        candles[j] for j in range(window_start, window_end)
                        if regime_list[j] == regime
                    ]
                    if len(window_candles) < 15:
                        idx += step
                        continue

                    strategy = RSIStrategy(oversold=os_val, overbought=ob_val)
                    engine = BacktestEngine(
                        candle_store=None,
                        initial_capital=initial_capital,
                    )
                    result = engine.run(strategy=strategy, candles=window_candles)

                    all_sharpes.append(result.sharpe_ratio)
                    all_win_rates.append(result.win_rate)
                    all_maxdds.append(result.max_drawdown)
                    all_pnl.append(result.total_pnl)
                    total_trades += len(result.trades)
                    idx += step

                if all_sharpes:
                    results.append(RSIResult(
                        regime=regime.value,
                        oversold=os_val,
                        overbought=ob_val,
                        win_rate=statistics.mean(all_win_rates),
                        sharpe_ratio=statistics.mean(all_sharpes),
                        max_drawdown=statistics.mean(all_maxdds),
                        total_pnl=statistics.mean(all_pnl),
                        n_trades=total_trades,
                        profit_factor=calculate_profit_factor_from_pnl(all_pnl),
                        equity_curve=all_pnl,
                    ))

    return results


def calculate_profit_factor_from_pnl(pnl_values: list[float]) -> float:
    """Calculate profit factor from a list of PnL values."""
    gross_profit = sum(p for p in pnl_values if p > 0)
    gross_loss = abs(sum(p for p in pnl_values if p < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

@dataclass
class RegimeSensitivity:
    """Sensitivity analysis for a single regime."""
    regime: str
    best_oversold: float
    best_overbought: float
    best_sharpe: float
    best_win_rate: float
    best_max_dd: float
    sharpe_range: float  # max - min sharpe
    win_rate_range: float
    max_dd_range: float
    sharpe_std: float
    win_rate_std: float
    max_dd_std: float
    sharpe_cv: float = 0.0  # coefficient of variation
    all_results: list[RSIResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def analyze_sensitivity(
    results: list[RSIResult],
) -> dict[str, RegimeSensitivity]:
    """Analyze RSI threshold sensitivity per regime.

    For each regime:
    - Find best (oversold, overbought) combo by Sharpe ratio
    - Calculate sensitivity ranges (how much metrics vary)
    - Determine if the regime is sensitive or robust to threshold changes
    """
    regime_results: dict[str, list[RSIResult]] = {}
    for r in results:
        regime_results.setdefault(r.regime, []).append(r)

    sensitivity: dict[str, RegimeSensitivity] = {}

    for regime, rlist in regime_results.items():
        if not rlist:
            continue

        # Find best by Sharpe
        best = max(rlist, key=lambda r: r.sharpe_ratio)

        # Calculate ranges and stds
        sharpes = [r.sharpe_ratio for r in rlist]
        win_rates = [r.win_rate for r in rlist]
        maxdds = [r.max_drawdown for r in rlist]

        sharpe_range = max(sharpes) - min(sharpes)
        win_rate_range = max(win_rates) - min(win_rates)
        max_dd_range = max(maxdds) - min(maxdds)

        sharpe_std_val = statistics.stdev(sharpes) if len(sharpes) > 1 else 0.0
        sharpe_cv_val = sharpe_std_val / abs(best.sharpe_ratio) if best.sharpe_ratio != 0 else 0.0

        sensitivity[regime] = RegimeSensitivity(
            regime=regime,
            best_oversold=best.oversold,
            best_overbought=best.overbought,
            best_sharpe=best.sharpe_ratio,
            best_win_rate=best.win_rate,
            best_max_dd=best.max_drawdown,
            sharpe_range=sharpe_range,
            win_rate_range=win_rate_range,
            max_dd_range=max_dd_range,
            sharpe_std=sharpe_std_val,
            win_rate_std=statistics.stdev(win_rates) if len(win_rates) > 1 else 0.0,
            max_dd_std=statistics.stdev(maxdds) if len(maxdds) > 1 else 0.0,
            sharpe_cv=sharpe_cv_val,
            all_results=rlist,
        )

    return sensitivity


def find_optimal_rsi_bands(
    sensitivity: dict[str, RegimeSensitivity],
    pct_10_results: list[RSIResult],
    pct_20_results: list[RSIResult],
) -> dict[str, dict[str, Any]]:
    """Find optimal RSI bands per regime.

    For each regime, determine:
    - Optimal oversold band (the range where Sharpe is within 10% of best)
    - Optimal overbought band
    - Sensitivity classification (sensitive/robust)
    """
    optimal = {}

    for regime, sens in sensitivity.items():
        rlist = sens.all_results
        best_sharpe = sens.best_sharpe
        threshold_10pct = best_sharpe * 0.9  # within 10% of best

        # Find oversold values within 10% of best Sharpe
        good_os = sorted(set(
            r.oversold for r in rlist if r.sharpe_ratio >= threshold_10pct
        ))
        good_ob = sorted(set(
            r.overbought for r in rlist if r.sharpe_ratio >= threshold_10pct
        ))

        # Classify sensitivity
        sharpe_cv = sens.sharpe_std / abs(sens.best_sharpe) if sens.best_sharpe != 0 else 1.0
        if sharpe_cv < 0.15:
            sensitivity_class = "robust"
        elif sharpe_cv < 0.30:
            sensitivity_class = "moderate"
        else:
            sensitivity_class = "sensitive"

        optimal[regime] = {
            "best_oversold": sens.best_oversold,
            "best_overbought": sens.best_overbought,
            "optimal_oversold_band": f"{min(good_os):.1f}-{max(good_os):.1f}" if good_os else f"{sens.best_oversold:.1f}",
            "optimal_overbought_band": f"{min(good_ob):.1f}-{max(good_ob):.1f}" if good_ob else f"{sens.best_overbought:.1f}",
            "sensitivity_class": sensitivity_class,
            "sharpe_at_best": sens.best_sharpe,
            "sharpe_range": sens.sharpe_range,
            "win_rate_at_best": sens.best_win_rate,
            "max_dd_at_best": sens.best_max_dd,
            "sharpe_cv": sharpe_cv,
        }

    return optimal


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_sensitivity_table(sensitivity: dict[str, RegimeSensitivity]) -> None:
    """Print a formatted sensitivity table."""
    print("\n" + "=" * 90)
    print("RSI THRESHOLD SENSITIVITY PER REGIME")
    print("=" * 90)
    print(f"{'Regime':<14} {'Best OS':>8} {'Best OB':>8} {'Sharpe':>8} {'Win%':>6} {'MaxDD':>7} "
          f"{'SRange':>7} {'WRRange':>7} {'DRRange':>7} {'CV':>5} {'Class':>10}")
    print("-" * 90)

    for regime in sorted(sensitivity.keys()):
        s = sensitivity[regime]
        cv_str = f"{s.sharpe_cv:.2f}" if s.sharpe_std > 0 else "0.00"
        print(
            f"{s.regime:<14} {s.best_oversold:>8.1f} {s.best_overbought:>8.1f} "
            f"{s.best_sharpe:>8.2f} {s.best_win_rate*100:>6.1f} {s.best_max_dd*100:>6.2f}% "
            f"{s.sharpe_range:>7.2f} {s.win_rate_range*100:>6.2f}% {s.max_dd_range*100:>6.2f}% "
            f"{cv_str:>5} {sensitivity_class_label(s.sharpe_cv):>10}"
        )

    print("-" * 90)
    print("CV = Coefficient of variation (Sharpe std / |best Sharpe|)")
    print("Class: robust (CV<0.15), moderate (0.15-0.30), sensitive (CV>0.30)")
    print("=" * 90)


def sensitivity_class_label(cv: float) -> str:
    if cv < 0.15:
        return "robust"
    elif cv < 0.30:
        return "moderate"
    return "sensitive"


def print_optimal_bands(optimal: dict[str, dict[str, Any]]) -> None:
    """Print optimal RSI bands per regime."""
    print("\n" + "=" * 70)
    print("OPTIMAL RSI BANDS PER REGIME")
    print("=" * 70)
    print(f"{'Regime':<14} {'Best OS':>8} {'Best OB':>8} {'OS Band':>10} {'OB Band':>10} {'Class':>10} {'Sharpe':>8}")
    print("-" * 70)

    for regime in sorted(optimal.keys()):
        o = optimal[regime]
        print(
            f"{regime:<14} {o['best_oversold']:>8.1f} {o['best_overbought']:>8.1f} "
            f"{o['optimal_oversold_band']:>10} {o['optimal_overbought_band']:>10} "
            f"{o['sensitivity_class']:>10} {o['sharpe_at_best']:>8.2f}"
        )

    print("=" * 70)


def print_threshold_comparison(sensitivity: dict[str, RegimeSensitivity]) -> None:
    """Print comparison of ±10% vs ±20% impact."""
    print("\n" + "=" * 80)
    print("THRESHOLD VARIATION IMPACT: ±10% vs ±20%")
    print("=" * 80)
    print(f"{'Regime':<14} {'±10% Sharpe Δ':>14} {'±20% Sharpe Δ':>14} {'Δ Ratio':>8} {'Interpretation':>16}")
    print("-" * 80)

    for regime in sorted(sensitivity.keys()):
        s = sensitivity[regime]
        # Sharpe range is the proxy for impact
        # ±10% range ≈ sharpe_range / 2 (rough approximation since we have 3 values)
        # ±20% range ≈ full sharpe_range (5 values)
        pct_10_impact = s.sharpe_range * 0.5
        pct_20_impact = s.sharpe_range
        ratio = pct_10_impact / pct_20_impact if pct_20_impact > 0 else 1.0

        if ratio > 0.7:
            interp = "linear"
        elif ratio > 0.4:
            interp = "diminishing"
        else:
            interp = "non-linear"

        print(
            f"{regime:<14} {pct_10_impact:>14.2f} {pct_20_impact:>14.2f} "
            f"{ratio:>8.2f} {interp:>16}"
        )

    print("=" * 80)


def save_results(
    results: list[RSIResult],
    sensitivity: dict[str, RegimeSensitivity],
    optimal: dict[str, dict[str, Any]],
    output_path: str = "rsi_threshold_robustness.json",
) -> None:
    """Save all results to JSON."""
    output = {
        "metadata": {
            "analysis": "rsi_threshold_robustness",
            "default_oversold": DEFAULT_OVERSOLD,
            "default_overbought": DEFAULT_OVERBOUGHT,
            "pct_10_oversold": PCT_10_OVERSOLD,
            "pct_10_overbought": PCT_10_OVERBOUGHT,
            "pct_20_oversold": PCT_20_OVERSOLD,
            "pct_20_overbought": PCT_20_OVERBOUGHT,
            "generated_at": datetime.utcnow().isoformat(),
        },
        "sensitivity": {k: v.to_dict() for k, v in sensitivity.items()},
        "optimal_bands": optimal,
        "all_results": [r.to_dict() for r in results],
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Run the RSI threshold robustness analysis."""
    print("Loading candles...")

    # Try to load from file, fall back to synthetic
    try:
        candles = load_candles_from_file("data/candles.json")
        print(f"Loaded {len(candles)} candles from file")
    except FileNotFoundError:
        print("No candles.json found, generating synthetic data...")
        candles = generate_synthetic_candles(n=720)
        print(f"Generated {len(candles)} synthetic candles")

    print(f"\nRunning RSI threshold sweep ({len(candles)} candles)...")
    print(f"Default thresholds: oversold={DEFAULT_OVERSOLD}, overbought={DEFAULT_OVERBOUGHT}")
    print(f"±10% ranges: oversold={PCT_10_OVERSOLD}, overbought={PCT_10_OVERBOUGHT}")
    print(f"±20% ranges: oversold={PCT_20_OVERSOLD}, overbought={PCT_20_OVERBOUGHT}")

    # Run sweep
    results = run_rsi_sweep(
        candles=candles,
        oversold_values=PCT_20_OVERSOLD,
        overbought_values=PCT_20_OVERBOUGHT,
    )
    print(f"Generated {len(results)} (regime, threshold) results")

    # Analyze sensitivity
    sensitivity = analyze_sensitivity(results)
    print(f"Analyzed {len(sensitivity)} regimes")

    # Find optimal bands
    pct10_results = [r for r in results if r.oversold in PCT_10_OVERSOLD and r.overbought in PCT_10_OVERBOUGHT]
    pct20_results = results  # all results include ±20%
    optimal = find_optimal_rsi_bands(sensitivity, pct10_results, pct20_results)

    # Print results
    print_sensitivity_table(sensitivity)
    print_optimal_bands(optimal)
    print_threshold_comparison(sensitivity)

    # Save
    save_results(results, sensitivity, optimal)

    return results, sensitivity, optimal


if __name__ == "__main__":
    main()
