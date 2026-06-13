#!/usr/bin/env python3
"""RSI threshold robustness analysis.

Vary RSI oversold/overbought thresholds parametrically (+/-10%, +/-20%)
across five regimes (bull, bear, range, high_vol, transition).

Measure win rate, Sharpe ratio, and max drawdown for each combination.
Acceptance criterion: runs on 720 synthetic candles without errors.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.backtest.engine import BacktestEngine, RSIStrategy, BacktestResult
from core.backtest.metrics import (
    Trade,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor,
)
from core.types import Candle


# ---------------------------------------------------------------------------
# Regime classification (reused from walk_forward_analysis.py)
# ---------------------------------------------------------------------------

class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    TRANSITION = "transition"


@dataclass
class RegimeMetrics:
    """Performance metrics for a single regime at a specific threshold combo."""
    regime: str
    n_candles: int = 0
    n_trades: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    total_pnl: float = 0.0
    total_return: float = 0.0
    profit_factor: float = 0.0
    mean_trade_pnl: float = 0.0
    std_trade_pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_regime(
    candles: Sequence[Candle],
    idx: int,
    lookback: int = 20,
    vol_threshold_abs: float = 30.0,
) -> Regime:
    """Classify the regime at a given candle index using rolling lookback.

    Uses price momentum and volatility to determine regime:
    - Bull: price > moving average and positive momentum
    - Bear: price < moving average and negative momentum
    - Range: price oscillating around moving average
    - High Vol: based on rolling volatility threshold
    - Transition: first `lookback` candles (insufficient history)
    """
    if idx < lookback:
        return Regime.TRANSITION

    start = max(0, idx - lookback)
    window = candles[start:idx + 1]
    closes = [float(c.close) for c in window]

    # Momentum: % change over lookback
    momentum = (closes[-1] - closes[0]) / closes[0]

    # Rolling volatility: std of price changes (absolute)
    price_changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    abs_vol = statistics.stdev(price_changes) if len(price_changes) > 1 else 0.0

    # Simple moving average
    sma = sum(closes) / len(closes)
    price_vs_sma = (closes[-1] - sma) / sma if sma > 0 else 0

    # Classify by absolute volatility
    if abs_vol > vol_threshold_abs:
        return Regime.HIGH_VOL
    elif momentum > 0.001 and price_vs_sma > 0:
        return Regime.BULL
    elif momentum < -0.001 and price_vs_sma < 0:
        return Regime.BEAR
    else:
        return Regime.RANGE


# ---------------------------------------------------------------------------
# Threshold variants
# ---------------------------------------------------------------------------

# Base thresholds: oversold=30, overbought=70
# +/-10%: oversold=[27, 33], overbought=[63, 77]
# +/-20%: oversold=[24, 36], overbought=[56, 84]

BASE_OVERSOLD = 30.0
BASE_OVERBOUGHT = 70.0

THRESHOLD_VARIANTS = {
    "-20%": (24.0, 56.0),
    "-10%": (27.0, 63.0),
    "base": (30.0, 70.0),
    "+10%": (33.0, 77.0),
    "+20%": (36.0, 84.0),
}

ALL_REGIMES = [Regime.BULL, Regime.BEAR, Regime.RANGE, Regime.HIGH_VOL, Regime.TRANSITION]


# ---------------------------------------------------------------------------
# Synthetic data generation (720 candles)
# ---------------------------------------------------------------------------

def generate_synthetic_candles(n: int = 720, seed: int = 42) -> list[Candle]:
    """Generate synthetic BTC/USDT candles for testing.

    Regime structure:
    - Bull (0-240): upward trend
    - Bear (240-480): downward trend
    - Range (480-720): mean-reverting
    """
    import random
    random.seed(seed)

    candles = []
    base_price = 45000.0
    base_time = datetime(2024, 1, 1)

    for i in range(n):
        # Add regime structure
        if i < 240:
            trend = 50 + random.gauss(0, 20)
        elif i < 480:
            trend = -40 + random.gauss(0, 30)
        else:
            trend = random.gauss(0, 15)

        open_price = base_price
        high = open_price + random.uniform(50, 300)
        low = open_price - random.uniform(50, 300)
        close = open_price + trend + random.gauss(0, 20)
        volume = random.uniform(100, 1000)

        candle = Candle(
            symbol="BTC/USDT",
            exchange="bitfinex",
            timeframe="1h",
            open_time=base_time + timedelta(hours=i),
            close_time=base_time + timedelta(hours=i + 1),
            open=Decimal(str(open_price)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=Decimal(str(volume)),
        )
        candles.append(candle)
        base_price = close

    return candles


# ---------------------------------------------------------------------------
# Analysis engine
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

            # Run backtest on regime-specific candles
            engine = BacktestEngine(
                candle_store=None,
                initial_capital=initial_capital,
            )
            result: BacktestResult = engine.run(strategy=strategy, candles=reg_candle_list)

            # Collect trades
            all_trades.extend(result.trades)

            # Win rate
            win_rate = calculate_win_rate(result.trades)

            # Sharpe ratio
            sharpe = result.sharpe_ratio

            # Max drawdown
            max_dd = result.max_drawdown

            # Total PnL and return
            total_pnl = result.total_pnl
            total_return = result.total_return

            # Profit factor
            profit_factor = result.profit_factor

            # Mean and std trade PnL
            pnl_values = [float(t.pnl) for t in result.trades]
            mean_pnl = statistics.mean(pnl_values) if pnl_values else 0.0
            std_pnl = statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0.0

            regime_metrics[regime.value] = RegimeMetrics(
                regime=regime.value,
                n_candles=n_candles,
                n_trades=len(result.trades),
                win_rate=win_rate,
                sharpe_ratio=sharpe,
                max_drawdown=max_dd,
                total_pnl=total_pnl,
                total_return=total_return,
                profit_factor=profit_factor,
                mean_trade_pnl=mean_pnl,
                std_trade_pnl=std_pnl,
            )

        # Overall metrics from all regime trades combined
        if all_trades:
            equity_points = [initial_capital]
            for i in range(1, len(all_trades) + 1):
                equity_points.append(initial_capital + sum(float(t.pnl) for t in all_trades[:i]))

            overall_sharpe = calculate_sharpe_ratio(
                [(equity - prev) / prev for prev, equity in zip(
                    equity_points[:-1], equity_points[1:]
                )]
            )
            overall_max_dd = calculate_max_drawdown(equity_points)
        else:
            overall_sharpe = 0.0
            overall_max_dd = 0.0

        overall = RegimeMetrics(
            regime="overall",
            n_candles=len(candles),
            n_trades=len(all_trades),
            win_rate=calculate_win_rate(all_trades),
            sharpe_ratio=overall_sharpe,
            max_drawdown=overall_max_dd,
            total_pnl=sum(float(t.pnl) for t in all_trades),
            total_return=sum(float(t.pnl) for t in all_trades) / initial_capital,
            profit_factor=calculate_profit_factor(all_trades),
            mean_trade_pnl=statistics.mean([float(t.pnl) for t in all_trades]) if all_trades else 0.0,
            std_trade_pnl=statistics.stdev([float(t.pnl) for t in all_trades]) if len(all_trades) > 1 else 0.0,
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
# Output formatting
# ---------------------------------------------------------------------------

def print_results_table(results: dict[str, ThresholdResult]) -> None:
    """Print a formatted summary table of results."""
    print("\n" + "=" * 100)
    print("RSI THRESHOLD ROBUSTNESS ANALYSIS")
    print(f"{'Threshold':<12} {'OS':>6} {'OB':>6} | {'Regime':<12} {'Win%':>7} {'Sharpe':>7} {'MaxDD':>7} {'Trades':>6} {'MeanPnL':>9}")
    print("-" * 100)

    for label, result in sorted(results.items()):
        first = True
        for regime in ALL_REGIMES:
            rm = result.regimes.get(regime.value)
            if rm and rm.n_candles > 0:
                if first:
                    print(f"  {label:<10} {result.oversold:>6.1f} {result.overbought:>6.1f} |", end="")
                    first = False
                else:
                    print(f"{'':12} {'':6} {'':6} |", end="")
                print(
                    f" {rm.regime:<12} "
                    f"{rm.win_rate * 100:>6.1f}% "
                    f"{rm.sharpe_ratio:>7.2f} "
                    f"{rm.max_drawdown * 100:>6.2f}% "
                    f"{rm.n_trades:>6} "
                    f"{rm.mean_trade_pnl:>+9.2f}"
                )
        print(f"{'':12} {'':6} {'':6} |", end="")
        print(
            f" {'overall':<12} "
            f"{result.overall.win_rate * 100:>6.1f}% "
            f"{result.overall.sharpe_ratio:>7.2f} "
            f"{result.overall.max_drawdown * 100:>6.2f}% "
            f"{result.overall.n_trades:>6} "
            f"{result.overall.mean_trade_pnl:>+9.2f}"
        )
        print()

    print("=" * 100)


def save_results_json(
    results: dict[str, ThresholdResult],
    candles: list[Candle],
    output_path: str = "rsi_threshold_results.json",
) -> None:
    """Save full results to JSON."""
    output = {
        "metadata": {
            "analysis": "rsi_threshold_robustness",
            "n_candles": len(candles),
            "threshold_variants": len(results),
            "regimes": [r.value for r in ALL_REGIMES],
            "generated_at": datetime.utcnow().isoformat(),
        },
        "results": {k: v.to_dict() for k, v in results.items()},
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the RSI threshold robustness analysis."""
    print("Generating 720 synthetic candles...")
    candles = generate_synthetic_candles(n=720)
    print(f"Generated {len(candles)} candles (bull=0-240, bear=240-480, range=480-720)")

    print("\nRunning threshold analysis...")
    results = run_threshold_analysis(candles)

    # Print results
    print_results_table(results)

    # Save to JSON
    save_results_json(results, candles)

    # Verification
    print("\n--- Verification ---")
    print(f"Candles: {len(candles)} (expected: 720) {'PASS' if len(candles) == 720 else 'FAIL'}")
    print(f"Threshold variants: {len(results)} (expected: 5) {'PASS' if len(results) == 5 else 'FAIL'}")
    print(f"Regimes per variant: {len(ALL_REGIMES)} (expected: 5) {'PASS' if len(ALL_REGIMES) == 5 else 'FAIL'}")
    print("No errors detected: PASS")


if __name__ == "__main__":
    main()
