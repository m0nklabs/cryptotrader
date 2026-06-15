#!/usr/bin/env python3
"""Walk-forward backtest analysis across bull/bear/range regimes.

Uses rolling windows (20-candle lookback, 5-trade evaluation window)
to capture regime-dependent performance with statistical significance.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from dataclasses import dataclass, field, asdict
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
from core.backtest.metrics import Trade, calculate_sharpe_ratio, calculate_max_drawdown, calculate_win_rate, calculate_profit_factor
from core.types import Candle
# from core.persistence.file_candle_store import FileCandleStore


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------

class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"
    TRANSITION = "transition"


@dataclass
class RegimeMetrics:
    """Performance metrics for a single regime across all walk-forward windows."""
    regime: str
    n_windows: int = 0
    n_candles: int = 0
    n_trades: int = 0
    total_pnl: float = 0.0
    total_return: float = 0.0
    mean_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    mean_trade_pnl: float = 0.0
    std_trade_pnl: float = 0.0
    t_stat: float = 0.0  # t-statistic for mean trade PnL != 0
    p_value: float = 0.0  # two-tailed p-value
    significant: bool = False  # p < 0.05
    equity_curve: list[float] = field(default_factory=list)
    trade_pnl_series: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop('equity_curve', None)
        d.pop('trade_pnl_series', None)
        return d


def classify_regime(
    candles: Sequence[Candle],
    idx: int,
    lookback: int = 20,
    vol_threshold_pct: float = 0.002,  # ~0.2% hourly vol threshold
    vol_threshold_abs: float = 30.0,     # absolute price movement threshold
) -> Regime:
    """Classify the regime at a given candle index using rolling lookback.

    Uses price momentum and volatility to determine regime:
    - Bull: price > moving average and positive momentum
    - Bear: price < moving average and negative momentum
    - Range: price oscillating around moving average
    - High/Low Vol: based on rolling volatility threshold
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
    elif abs_vol < vol_threshold_abs * 0.5:
        return Regime.LOW_VOL
    elif momentum > 0.001 and price_vs_sma > 0:
        return Regime.BULL
    elif momentum < -0.001 and price_vs_sma < 0:
        return Regime.BEAR
    else:
        return Regime.RANGE


# ---------------------------------------------------------------------------
# Walk-forward engine
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardWindow:
    """A single walk-forward window result."""
    start_idx: int
    end_idx: int
    regime: Regime
    result: BacktestResult
    trades_in_window: list[Trade]
    equity_at_start: float
    equity_at_end: float


def run_walk_forward(
    candles: Sequence[Candle],
    strategy: RSIStrategy | None = None,
    initial_capital: float = 10000.0,
    lookback: int = 20,
    trade_window: int = 5,
    overlap: int = 5,
    step: int = 10,
    use_adaptive_rsi: bool = True,
) -> list[WalkForwardWindow]:
    """Run walk-forward backtest with rolling windows.

    Args:
        candles: Full candle sequence
        strategy: Strategy to use (defaults to RSIStrategy with adaptive thresholds)
        initial_capital: Starting equity
        lookback: Number of candles for lookback/lookahead
        trade_window: Number of trades to evaluate per window
        overlap: Overlap between consecutive windows
        step: Step size between windows
        use_adaptive_rsi: Use adaptive RSI thresholds based on data volatility
    """
    if strategy is None:
        # Use adaptive RSI thresholds for synthetic data
        if use_adaptive_rsi:
            # For synthetic BTC data, use wider RSI thresholds
            strategy = RSIStrategy(oversold=40.0, overbought=85.0)
        else:
            strategy = RSIStrategy()

    engine = BacktestEngine(
        candle_store=None,
        initial_capital=initial_capital,
    )

    windows: list[WalkForwardWindow] = []
    equity = initial_capital

    # Walk through candles in steps
    idx = lookback
    while idx < len(candles) - step:
        # Define window boundaries
        window_start = max(0, idx - lookback)
        window_end = min(idx + lookback, len(candles))
        window_candles = candles[window_start:window_end]

        # Classify regime
        regime = classify_regime(candles, idx, lookback=lookback)

        # Run backtest on this window
        result = engine.run(strategy=strategy, candles=window_candles)

        # Track trades within this window
        trades_in_window = result.trades[-trade_window:] if len(result.trades) > trade_window else result.trades

        windows.append(WalkForwardWindow(
            start_idx=window_start,
            end_idx=window_end,
            regime=regime,
            result=result,
            trades_in_window=trades_in_window,
            equity_at_start=equity,
            equity_at_end=result.equity_curve[-1] if result.equity_curve else equity,
        ))

        # Update equity for next window
        equity = result.equity_curve[-1] if result.equity_curve else equity

        # Advance
        idx += step - overlap

    return windows


# ---------------------------------------------------------------------------
# Aggregate metrics per regime
# ---------------------------------------------------------------------------

def aggregate_regime_metrics(
    windows: list[WalkForwardWindow],
) -> dict[Regime, RegimeMetrics]:
    """Aggregate walk-forward results into per-regime metrics with stats."""
    regime_data: dict[Regime, list[WalkForwardWindow]] = {}
    for w in windows:
        regime_data.setdefault(w.regime, []).append(w)

    results: dict[Regime, RegimeMetrics] = {}

    for regime, wlist in regime_data.items():
        rm = RegimeMetrics(regime=regime.value)
        rm.n_windows = len(wlist)

        # Aggregate candles and trades
        rm.n_candles = sum(w.end_idx - w.start_idx for w in wlist)
        all_trades = []
        for w in wlist:
            all_trades.extend(w.trades_in_window)
        rm.n_trades = len(all_trades)

        # Aggregate PnL and returns
        rm.total_pnl = sum(float(t.pnl) for t in all_trades)
        returns_list = [w.equity_at_end / w.equity_at_start - 1 for w in wlist if w.equity_at_start > 0]
        rm.total_return = sum(returns_list)
        rm.mean_return = statistics.mean(returns_list) if returns_list else 0.0

        # Sharpe ratio (annualized, assuming each window is ~1 day for 1h candles)
        if returns_list:
            rm.sharpe_ratio = calculate_sharpe_ratio(returns_list, trading_days=365)

        # Max drawdown across all windows
        all_equity = []
        for w in wlist:
            all_equity.extend(w.result.equity_curve)
        rm.max_drawdown = calculate_max_drawdown(all_equity) if all_equity else 0.0

        # Win rate
        rm.win_rate = calculate_win_rate(all_trades)

        # Profit factor
        rm.profit_factor = calculate_profit_factor(all_trades)

        # Mean and std of trade PnL
        pnl_values = [float(t.pnl) for t in all_trades]
        rm.trade_pnl_series = pnl_values
        rm.mean_trade_pnl = statistics.mean(pnl_values) if pnl_values else 0.0
        rm.std_trade_pnl = statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0.0

        # T-statistic and p-value (two-tailed test: mean != 0)
        if len(pnl_values) > 1 and rm.std_trade_pnl > 0:
            se = rm.std_trade_pnl / math.sqrt(len(pnl_values))
            rm.t_stat = rm.mean_trade_pnl / se
            # Approximate p-value using normal distribution for large n
            # Using error function approximation
            rm.p_value = 2 * (1 - _normal_cdf(abs(rm.t_stat)))
            rm.significant = rm.p_value < 0.05
        else:
            rm.t_stat = 0.0
            rm.p_value = 1.0
            rm.significant = False

        # Collect equity curve from last window for visualization
        if wlist:
            last = wlist[-1]
            rm.equity_curve = last.result.equity_curve

        results[regime] = rm

    return results


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF using error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_regime_summary(metrics: dict[Regime, RegimeMetrics]) -> None:
    """Print a formatted summary of regime performance."""
    print("\n" + "=" * 70)
    print("WALK-FORWARD ANALYSIS: REGIME-BASED PERFORMANCE")
    print("=" * 70)

    header = f"{'Regime':<12} {'Windows':>7} {'Trades':>6} {'Mean PnL':>10} {'Std PnL':>8} {'T-stat':>7} {'p-val':>7} {'Sig':>4} {'Win%':>6} {'Sharpe':>7} {'PF':>5} {'MaxDD':>7}"
    print(header)
    print("-" * len(header))

    for regime in [Regime.BULL, Regime.BEAR, Regime.RANGE, Regime.HIGH_VOL, Regime.LOW_VOL, Regime.TRANSITION]:
        if regime not in metrics:
            continue
        m = metrics[regime]
        line = (
            f"{m.regime:<12} {m.n_windows:>7} {m.n_trades:>6} "
            f"{m.mean_trade_pnl:>+10.2f} {m.std_trade_pnl:>8.2f} "
            f"{m.t_stat:>+7.2f} {m.p_value:>7.3f} "
            f"{'***' if m.significant else '   ':>4} "
            f"{m.win_rate*100:>6.1f} {m.sharpe_ratio:>7.2f} "
            f"{m.profit_factor:>5.2f} {m.max_drawdown*100:>6.2f}%"
        )
        sig_marker = " ***" if m.significant else ""
        print(f"{line}{sig_marker}")

    print("\n" + "-" * 70)
    print("Significance: *** p < 0.05 (two-tailed t-test, mean trade PnL != 0)")
    print("=" * 70)


def build_regime_curves(
    windows: list[WalkForwardWindow],
    metrics: dict[Regime, RegimeMetrics],
) -> dict[str, dict[str, list]]:
    """Build performance curves for each regime."""
    curves: dict[str, dict[str, list]] = {}

    for regime in [Regime.BULL, Regime.BEAR, Regime.RANGE, Regime.HIGH_VOL, Regime.LOW_VOL, Regime.TRANSITION]:
        regime_windows = [w for w in windows if w.regime == regime]
        if not regime_windows:
            continue

        # Cumulative PnL curve
        cum_pnl = 0.0
        pnl_curve = [0.0]
        for w in regime_windows:
            cum_pnl += sum(float(t.pnl) for t in w.trades_in_window)
            pnl_curve.append(cum_pnl)

        # Equity curve (normalized to start)
        eq_curve = []
        for w in regime_windows:
            eq_curve.append(w.equity_at_end / w.equity_at_start)

        curves[regime.value] = {
            "window_idx": list(range(len(pnl_curve))),
            "cumulative_pnl": pnl_curve,
            "equity_ratio": eq_curve,
            "win_rate": [metrics[regime].win_rate] * len(pnl_curve),
        }

    return curves


def save_results(
    windows: list[WalkForwardWindow],
    metrics: dict[Regime, RegimeMetrics],
    curves: dict[str, dict[str, list]],
    output_path: str = "walk_forward_results.json",
) -> None:
    """Save walk-forward results to JSON."""
    output = {
        "metadata": {
            "analysis": "walk-forward",
            "lookback": 20,
            "trade_window": 5,
            "total_windows": len(windows),
            "total_candles": len(windows) * 20 if windows else 0,
            "regimes_analyzed": list(metrics.keys()),
            "generated_at": datetime.utcnow().isoformat(),
        },
        "regime_metrics": {k.value: v.to_dict() for k, v in metrics.items()},
        "performance_curves": curves,
        "window_details": [
            {
                "start_idx": w.start_idx,
                "end_idx": w.end_idx,
                "regime": w.regime.value,
                "total_pnl": float(sum(float(t.pnl) for t in w.trades_in_window)),
                "n_trades": len(w.trades_in_window),
                "equity_start": w.equity_at_start,
                "equity_end": w.equity_at_end,
            }
            for w in windows
        ],
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_candles_from_file(filepath: str = "data/candles.json") -> list[Candle]:
    """Load candles from a JSON file."""
    with open(filepath) as f:
        data = json.load(f)

    candles = []
    for item in data:
        if isinstance(item, dict):
            c = Candle(
                symbol=item.get("symbol", "BTC/USDT"),
                exchange=item.get("exchange", "bitfinex"),
                timeframe=item.get("timeframe", "1h"),
                open_time=datetime.fromisoformat(item["open_time"]) if isinstance(item["open_time"], str) else item["open_time"],
                close_time=datetime.fromisoformat(item["close_time"]) if isinstance(item["close_time"], str) else item["close_time"],
                open=Decimal(str(item["open"])),
                high=Decimal(str(item["high"])),
                low=Decimal(str(item["low"])),
                close=Decimal(str(item["close"])),
                volume=Decimal(str(item["volume"])),
            )
            candles.append(c)
    return candles


def generate_synthetic_candles(n: int = 720, seed: int = 42) -> list[Candle]:
    """Generate synthetic BTC/USDT candles for testing."""
    import random
    random.seed(seed)

    candles = []
    base_price = 45000.0
    base_time = datetime(2024, 1, 1)

    for i in range(n):
        # Add regime structure: bull (0-240), bear (240-480), range (480-720)
        if i < 240:
            # Bull trend
            trend = 50 + random.gauss(0, 20)
        elif i < 480:
            # Bear trend
            trend = -40 + random.gauss(0, 30)
        else:
            # Range bound
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


def main():
    """Run the walk-forward analysis."""
    print("Loading candles...")

    # Try to load from file, fall back to synthetic
    try:
        candles = load_candles_from_file("data/candles.json")
        print(f"Loaded {len(candles)} candles from file")
    except FileNotFoundError:
        print("No candles.json found, generating synthetic data...")
        candles = generate_synthetic_candles(n=720)
        print(f"Generated {len(candles)} synthetic candles")

    print(f"Running walk-forward analysis ({len(candles)} candles, lookback=20, trade_window=5)...")

    # Run walk-forward
    windows = run_walk_forward(
        candles=candles,
        lookback=20,
        trade_window=5,
        overlap=5,
        step=10,
    )
    print(f"Generated {len(windows)} walk-forward windows")

    # Aggregate metrics
    metrics = aggregate_regime_metrics(windows)

    # Print summary
    print_regime_summary(metrics)

    # Build and save curves
    curves = build_regime_curves(windows, metrics)
    save_results(windows, metrics, curves, "walk_forward_results.json")

    # Print statistical significance summary
    print("\nStatistical Significance Summary:")
    print("-" * 40)
    for regime, m in sorted(metrics.items(), key=lambda x: x[1].p_value):
        sig = "SIGNIFICANT" if m.significant else "not significant"
        print(f"  {regime.value:12} p={m.p_value:.4f} t={m.t_stat:.2f}  [{sig}]")

    return metrics


if __name__ == "__main__":
    main()
