#!/usr/bin/env python3
"""Regime underperformance analysis.

Compute per-regime metrics (return, drawdown, Sharpe, win rate) against
the transition baseline. Apply threshold logic to flag bear/range underperformance.

Acceptance: Script runs end-to-end, outputs intermediate metrics, and correctly
classifies regimes against live thresholds.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
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
    LOW_VOL = "low_vol"
    TRANSITION = "transition"


# ---------------------------------------------------------------------------
# Underperformance thresholds (live thresholds for flagging)
# ---------------------------------------------------------------------------

@dataclass
class UnderperformanceThresholds:
    """Live thresholds for flagging underperformance per regime.

    A regime is flagged as underperforming when its metrics fall below
    the transition baseline by more than the threshold.
    """
    # Return: regime return must be >= (transition_return - return_threshold)
    return_threshold: float = 0.00005  # per-candle return threshold
    # Drawdown: regime drawdown must be <= (transition_drawdown + dd_threshold)
    drawdown_threshold: float = 0.05  # 5% additional drawdown tolerance
    # Sharpe: regime sharpe must be >= (transition_sharpe - sharpe_threshold)
    sharpe_threshold: float = 0.3  # Sharpe drop threshold
    # Win rate: regime win rate must be >= (transition_win_rate - wr_threshold)
    win_rate_threshold: float = 0.05  # 5% win rate drop threshold
    # Underperformance score: weighted combination
    # A regime is underperforming if score > threshold
    underperformance_score_threshold: float = 2.0


# ---------------------------------------------------------------------------
# Per-regime metrics
# ---------------------------------------------------------------------------

@dataclass
class RegimeMetrics:
    """Performance metrics for a single regime."""
    regime: str
    n_candles: int = 0
    n_trades: int = 0
    total_return: float = 0.0
    mean_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_pnl: float = 0.0
    mean_trade_pnl: float = 0.0
    std_trade_pnl: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    trade_pnl_series: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop('equity_curve', None)
        d.pop('trade_pnl_series', None)
        return d


@dataclass
class UnderperformanceFlag:
    """Underperformance flag for a single regime."""
    regime: str
    is_underperforming: bool
    score: float  # 0 = no underperformance, higher = worse
    return_delta: float = 0.0  # regime_return - transition_return
    drawdown_delta: float = 0.0
    sharpe_delta: float = 0.0
    win_rate_delta: float = 0.0
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Transition baseline computation
# ---------------------------------------------------------------------------

def compute_transition_baseline(
    candles: Sequence[Candle],
    lookback: int = 20,
    vol_threshold_abs: float = 30.0,
) -> dict[str, Any]:
    """Compute the transition baseline from transition-regime candles.

    The transition baseline serves as the reference point for comparing
    other regimes. It represents 'normal' market conditions.
    """
    # Classify all candles and extract transition ones
    transition_candles = []
    for i, c in enumerate(candles):
        regime = classify_regime(candles, i, lookback, vol_threshold_abs)
        if regime == Regime.TRANSITION:
            transition_candles.append(c)

    if not transition_candles:
        # Fallback: use all candles as baseline
        transition_candles = candles

    # Compute metrics on transition candles
    returns = []
    price_changes = []
    for i in range(1, len(transition_candles)):
        prev_close = float(transition_candles[i - 1].close)
        curr_close = float(transition_candles[i].close)
        ret = (curr_close - prev_close) / prev_close if prev_close > 0 else 0.0
        returns.append(ret)
        price_changes.append(curr_close - prev_close)

    transition_return = statistics.mean(returns) if returns else 0.0
    transition_sharpe = calculate_sharpe_ratio(returns) if returns else 0.0
    transition_drawdown = calculate_max_drawdown(
        [float(c.close) for c in transition_candles]
    ) if transition_candles else 0.0

    return {
        "return": transition_return,
        "sharpe": transition_sharpe,
        "drawdown": transition_drawdown,
        "n_candles": len(transition_candles),
    }


# ---------------------------------------------------------------------------
# Per-regime metric computation
# ---------------------------------------------------------------------------

def classify_regime(
    candles: Sequence[Candle],
    idx: int,
    lookback: int = 20,
    vol_threshold_abs: float = 30.0,
) -> Regime:
    """Classify the regime at a given candle index using rolling lookback."""
    if idx < lookback:
        return Regime.TRANSITION

    start = max(0, idx - lookback)
    window = candles[start:idx + 1]
    closes = [float(c.close) for c in window]

    momentum = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0.0
    price_changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    abs_vol = statistics.stdev(price_changes) if len(price_changes) > 1 else 0.0
    sma = sum(closes) / len(closes)
    price_vs_sma = (closes[-1] - sma) / sma if sma > 0 else 0

    if abs_vol > vol_threshold_abs:
        return Regime.HIGH_VOL
    elif abs_vol < vol_threshold_abs * 0.5:
        return Regime.LOW_VOL
    elif momentum > 0.001 and price_vs_sma > 0:
        return Regime.BULL
    elif momentum < -0.001 and price_vs_sma < 0:
        return Regime.BEAR
    else:
        return Regime.RANGE


def compute_regime_metrics(
    candles: Sequence[Candle],
    regime: Regime,
    lookback: int = 20,
    vol_threshold_abs: float = 30.0,
    initial_capital: float = 10000.0,
) -> RegimeMetrics:
    """Compute metrics for candles belonging to a specific regime."""
    regime_candles = []
    for i, c in enumerate(candles):
        if classify_regime(candles, i, lookback, vol_threshold_abs) == regime:
            regime_candles.append(c)

    if not regime_candles:
        return RegimeMetrics(regime=regime.value)

    # Compute returns
    returns = []
    for i in range(1, len(regime_candles)):
        prev_close = float(regime_candles[i - 1].close)
        curr_close = float(regime_candles[i].close)
        ret = (curr_close - prev_close) / prev_close if prev_close > 0 else 0.0
        returns.append(ret)

    # Run a simple backtest on regime candles
    strategy = RSIStrategy(oversold=30.0, overbought=70.0)
    engine = BacktestEngine(
        candle_store=None,
        initial_capital=initial_capital,
    )
    result: BacktestResult = engine.run(strategy=strategy, candles=regime_candles)

    # Compute metrics
    rm = RegimeMetrics(regime=regime.value)
    rm.n_candles = len(regime_candles)
    rm.n_trades = len(result.trades)
    rm.total_return = result.total_return
    rm.mean_return = statistics.mean(returns) if returns else 0.0
    rm.sharpe_ratio = result.sharpe_ratio
    rm.max_drawdown = result.max_drawdown
    rm.win_rate = result.win_rate
    rm.profit_factor = result.profit_factor
    rm.total_pnl = result.total_pnl
    rm.mean_trade_pnl = statistics.mean([float(t.pnl) for t in result.trades]) if result.trades else 0.0
    rm.std_trade_pnl = statistics.stdev([float(t.pnl) for t in result.trades]) if len(result.trades) > 1 else 0.0
    rm.trade_pnl_series = [float(t.pnl) for t in result.trades]
    rm.equity_curve = result.equity_curve

    return rm


def compute_all_regime_metrics(
    candles: Sequence[Candle],
    lookback: int = 20,
    vol_threshold_abs: float = 30.0,
    initial_capital: float = 10000.0,
) -> dict[Regime, RegimeMetrics]:
    """Compute metrics for all regimes."""
    results: dict[Regime, RegimeMetrics] = {}
    for regime in list(Regime):
        results[regime] = compute_regime_metrics(
            candles, regime, lookback, vol_threshold_abs, initial_capital
        )
    return results


# ---------------------------------------------------------------------------
# Underperformance analysis
# ---------------------------------------------------------------------------

def compute_underperformance(
    regime_metrics: dict[Regime, RegimeMetrics],
    transition_baseline: dict[str, Any],
    thresholds: UnderperformanceThresholds | None = None,
) -> dict[str, UnderperformanceFlag]:
    """Compute underperformance flags for each regime against transition baseline.

    A regime is flagged as underperforming when its metrics fall below
    the transition baseline by more than the threshold.

    Underperformance score is a weighted combination:
    score = sum of absolute deltas / thresholds
    """
    if thresholds is None:
        thresholds = UnderperformanceThresholds()

    trans_return = transition_baseline["return"]
    trans_sharpe = transition_baseline["sharpe"]
    trans_drawdown = transition_baseline["drawdown"]

    flags: dict[str, UnderperformanceFlag] = {}

    for regime, rm in regime_metrics.items():
        # Skip transition itself (it's the baseline)
        if regime == Regime.TRANSITION:
            flags[regime.value] = UnderperformanceFlag(
                regime=regime.value,
                is_underperforming=False,
                score=0.0,
                return_delta=0.0,
                drawdown_delta=0.0,
                sharpe_delta=0.0,
                win_rate_delta=0.0,
                flags=["baseline"],
            )
            continue

        # Compute deltas (regime - transition)
        return_delta = rm.mean_return - trans_return
        drawdown_delta = rm.max_drawdown - trans_drawdown  # positive = worse
        sharpe_delta = trans_sharpe - rm.sharpe_ratio  # positive = worse
        win_rate_delta = trans_win_rate(regime_metrics, regime) - rm.win_rate

        # Compute underperformance score (weighted)
        score = (
            abs(return_delta / thresholds.return_threshold) if thresholds.return_threshold != 0 else 0
        ) + (
            abs(drawdown_delta / thresholds.drawdown_threshold) if thresholds.drawdown_threshold != 0 else 0
        ) + (
            abs(sharpe_delta / thresholds.sharpe_threshold) if thresholds.sharpe_threshold != 0 else 0
        ) + (
            abs(win_rate_delta / thresholds.win_rate_threshold) if thresholds.win_rate_threshold != 0 else 0
        )

        # Determine flags
        flag_list = []
        if return_delta < -thresholds.return_threshold:
            flag_list.append("low_return")
        if drawdown_delta > thresholds.drawdown_threshold:
            flag_list.append("high_drawdown")
        if sharpe_delta > thresholds.sharpe_threshold:
            flag_list.append("low_sharpe")
        if win_rate_delta > thresholds.win_rate_threshold:
            flag_list.append("low_win_rate")

        is_underperforming = score > thresholds.underperformance_score_threshold

        flags[regime.value] = UnderperformanceFlag(
            regime=regime.value,
            is_underperforming=is_underperforming,
            score=score,
            return_delta=return_delta,
            drawdown_delta=drawdown_delta,
            sharpe_delta=sharpe_delta,
            win_rate_delta=win_rate_delta,
            flags=flag_list,
        )

    return flags


def trans_win_rate(
    regime_metrics: dict[Regime, RegimeMetrics],
    exclude: Regime,
) -> float:
    """Compute transition win rate as mean of all non-excluded regimes."""
    others = [rm.win_rate for r, rm in regime_metrics.items() if r != exclude]
    return statistics.mean(others) if others else 0.0


# ---------------------------------------------------------------------------
# OOS data loading
# ---------------------------------------------------------------------------

def load_oos_regime_data(
    filepath: str | None = None,
) -> dict[str, Any] | None:
    """Load OOS regime data from JSON file.

    Falls back to synthetic data if file not found.
    """
    if filepath is None:
        # Try default paths
        for p in [
            "oos_regime_dataset.json",
            "oos_regime_from_json.json",
            _project_root / "oos_regime_dataset.json",
            _project_root / "oos_regime_from_json.json",
        ]:
            if Path(p).exists():
                filepath = str(p)
                break

    if filepath and Path(filepath).exists():
        with open(filepath) as f:
            return json.load(f)

    return None


def oos_data_to_candles(
    oos_data: dict[str, Any],
) -> list[Candle]:
    """Convert OOS regime data to synthetic candles for analysis.

    Reconstructs candle sequences from segment data.
    """
    candles = []
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for segment in oos_data.get("segments", []):
        n = segment.get("n_candles", 1000)
        mean_ret = segment.get("mean_return", 0.0001)
        mean_vol = segment.get("mean_volatility", 0.02)
        mean_price = segment.get("mean_price", 40000.0)

        import random
        random.seed(hash(segment["name"]) % (2**31))

        price = mean_price
        for i in range(n):
            ret = random.gauss(mean_ret, mean_vol * 0.01)
            open_price = price
            close_price = open_price * (1 + ret)
            high = max(open_price, close_price) + random.uniform(10, 200)
            low = min(open_price, close_price) - random.uniform(10, 200)

            candles.append(Candle(
                symbol="BTC/USDT",
                exchange="bitfinex",
                timeframe="1h",
                open_time=base_time,
                close_time=base_time,
                open=Decimal(str(open_price)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close_price)),
                volume=Decimal(str(random.uniform(100, 1000))),
            ))
            base_time += __import__("datetime").timedelta(hours=1)
            price = close_price

    return candles


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_underperformance_summary(
    regime_metrics: dict[Regime, RegimeMetrics],
    transition_baseline: dict[str, Any],
    flags: dict[str, UnderperformanceFlag],
) -> None:
    """Print a formatted summary of regime underperformance."""
    print("\n" + "=" * 70)
    print("REGIME UNDERPERFORMANCE ANALYSIS")
    print("=" * 70)

    # Transition baseline
    print("\nTransition Baseline:")
    print(f"  Return:    {transition_baseline['return']:+.6f}")
    print(f"  Sharpe:    {transition_baseline['sharpe']:.4f}")
    print(f"  Drawdown:  {transition_baseline['drawdown']:.4f}")
    print(f"  Candles:   {transition_baseline['n_candles']}")

    # Per-regime metrics
    print("\n" + "-" * 70)
    header = (
        f"{'Regime':<12} {'Candles':>7} {'Trades':>6} "
        f"{'Return':>10} {'Sharpe':>7} {'Drawdown':>9} "
        f"{'Win%':>6} {'PF':>5}"
    )
    print(header)
    print("-" * len(header))

    for regime in [Regime.BULL, Regime.BEAR, Regime.RANGE, Regime.HIGH_VOL, Regime.TRANSITION]:
        if regime not in regime_metrics:
            continue
        rm = regime_metrics[regime]
        line = (
            f"{rm.regime:<12} {rm.n_candles:>7} {rm.n_trades:>6} "
            f"{rm.mean_return:>+10.6f} {rm.sharpe_ratio:>7.4f} "
            f"{rm.max_drawdown:>9.4f} "
            f"{rm.win_rate * 100:>5.1f}% {rm.profit_factor:>5.2f}"
        )
        flag = flags.get(regime.value)
        if flag and flag.is_underperforming:
            line += "  <-- UNDERPERFORMING"
        print(line)

    # Underperformance flags
    print("\n" + "-" * 70)
    print("Underperformance Flags:")
    print(f"  {'Regime':<12} {'Score':>6} {'ReturnΔ':>9} {'DDΔ':>7} "
          f"{'SharpeΔ':>8} {'WRΔ':>6}  Flags")
    print("  " + "-" * 55)

    for regime_name, flag in sorted(flags.items(), key=lambda x: -x[1].score):
        flag_str = ", ".join(flag.flags) if flag.flags else "none"
        print(
            f"  {regime_name:<12} {flag.score:>6.2f} "
            f"{flag.return_delta:>+9.6f} {flag.drawdown_delta:>+7.4f} "
            f"{flag.sharpe_delta:>+8.4f} {flag.win_rate_delta:>+6.4f}  {flag_str}"
        )

    # Summary
    underperforming = [name for name, f in flags.items() if f.is_underperforming]
    print("\n" + "=" * 70)
    if underperforming:
        print(f"Regimes flagged as underperforming: {', '.join(underperforming)}")
    else:
        print("No regimes flagged as underperforming.")
    print("=" * 70)


def save_results(
    regime_metrics: dict[Regime, RegimeMetrics],
    transition_baseline: dict[str, Any],
    flags: dict[str, UnderperformanceFlag],
    output_path: str = "regime_underperformance_results.json",
) -> None:
    """Save underperformance analysis results to JSON."""
    output = {
        "metadata": {
            "analysis": "regime_underperformance",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "transition_baseline": transition_baseline,
        },
        "regime_metrics": {k.value: v.to_dict() for k, v in regime_metrics.items()},
        "underperformance_flags": {k: v.to_dict() for k, v in flags.items()},
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_synthetic_candles(
    n: int = 720,
    seed: int = 42,
) -> list[Candle]:
    """Generate synthetic BTC/USDT candles for testing."""
    import random
    random.seed(seed)

    candles = []
    base_price = 45000.0
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for i in range(n):
        # Add regime structure: bull (0-240), bear (240-480), range (480-720)
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

        candles.append(Candle(
            symbol="BTC/USDT",
            exchange="bitfinex",
            timeframe="1h",
            open_time=base_time,
            close_time=base_time,
            open=Decimal(str(open_price)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=Decimal(str(volume)),
        ))
        base_time += __import__("datetime").timedelta(hours=1)
        base_price = close

    return candles


def main(
    candles: Sequence[Candle] | None = None,
    lookback: int = 20,
    vol_threshold_abs: float = 30.0,
    initial_capital: float = 10000.0,
    thresholds: UnderperformanceThresholds | None = None,
    output_path: str | None = None,
    load_oos: bool = True,
) -> dict[str, Any]:
    """Run the regime underperformance analysis.

    Args:
        candles: Optional candle sequence. If None, loads from OOS data or generates synthetic.
        lookback: Lookback window for regime classification.
        vol_threshold_abs: Absolute volatility threshold.
        initial_capital: Starting equity for backtest.
        thresholds: Underperformance thresholds. Defaults to live thresholds.
        output_path: Output JSON file path.
        load_oos: Whether to load OOS data first.
    """
    # Load or generate candles
    if candles is None:
        if load_oos:
            oos_data = load_oos_regime_data()
            if oos_data:
                candles = oos_data_to_candles(oos_data)
                print(f"Loaded {len(candles)} candles from OOS data")
            else:
                print("No OOS data found, generating synthetic candles...")
                candles = generate_synthetic_candles(n=720)
        else:
            candles = generate_synthetic_candles(n=720)

    print(f"Analyzing {len(candles)} candles...")

    # Compute transition baseline
    transition_baseline = compute_transition_baseline(
        candles, lookback, vol_threshold_abs
    )
    print(f"Transition baseline: return={transition_baseline['return']:+.6f}, "
          f"sharpe={transition_baseline['sharpe']:.4f}, "
          f"drawdown={transition_baseline['drawdown']:.4f}")

    # Compute per-regime metrics
    regime_metrics = compute_all_regime_metrics(
        candles, lookback, vol_threshold_abs, initial_capital
    )

    # Compute underperformance flags
    flags = compute_underperformance(regime_metrics, transition_baseline, thresholds)

    # Print summary
    print_underperformance_summary(regime_metrics, transition_baseline, flags)

    # Save results
    if output_path is None:
        output_path = "regime_underperformance_results.json"
    save_results(regime_metrics, transition_baseline, flags, output_path)

    return {
        "regime_metrics": {k.value: v.to_dict() for k, v in regime_metrics.items()},
        "transition_baseline": transition_baseline,
        "underperformance_flags": {k: v.to_dict() for k, v in flags.items()},
    }


if __name__ == "__main__":
    main()
