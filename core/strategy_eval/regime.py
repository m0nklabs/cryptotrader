"""Regime detection and per-regime strategy evaluation.

Detects market regimes (trending, ranging, high/low vol) and
evaluates strategy performance within each regime separately.
This helps identify strategies that only work in specific conditions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from core.strategy_eval.types import MarketRegime, RegimePerformance
from core.types import Candle


# ---------------------------------------------------------------------------
# Regime detector
# ---------------------------------------------------------------------------


@dataclass
class RegimeDetector:
    """Detects market regimes from candle data."""

    trend_window: int = 20  # SMA window for trend detection
    vol_window: int = 20  # volatility calculation window
    trend_threshold: float = 0.01  # % move for trend detection
    vol_z_threshold: float = 1.0  # z-score threshold for vol regime

    def detect_regime(self, candles: Sequence[Candle], index: int) -> MarketRegime:
        """Detect the regime at a specific candle index.

        Args:
            candles: Full candle sequence
            index: Current candle index

        Returns:
            Detected market regime
        """
        if index < self.trend_window:
            return MarketRegime.TRANSITION

        # Calculate trend direction and strength
        recent = candles[max(0, index - self.trend_window) : index + 1]
        trend = self._detect_trend(recent)

        # Calculate volatility regime
        vol_regime = self._detect_volatility(candles, index)

        # Combine trend and vol signals
        if trend == MarketRegime.TRENDING_UP:
            if vol_regime == MarketRegime.HIGH_VOL:
                return MarketRegime.HIGH_VOL
            return MarketRegime.TRENDING_UP
        elif trend == MarketRegime.TRENDING_DOWN:
            if vol_regime == MarketRegime.HIGH_VOL:
                return MarketRegime.HIGH_VOL
            return MarketRegime.TRENDING_DOWN
        else:
            if vol_regime == MarketRegime.HIGH_VOL:
                return MarketRegime.HIGH_VOL
            return MarketRegime.RANGING

    def detect_regimes(self, candles: Sequence[Candle]) -> list[MarketRegime]:
        """Detect regime for each candle.

        Args:
            candles: Full candle sequence

        Returns:
            List of regimes, one per candle
        """
        regimes = []
        for i in range(len(candles)):
            regime = self.detect_regime(candles, i)
            regimes.append(regime)
        return regimes

    def _detect_trend(self, candles: Sequence[Candle]) -> MarketRegime:
        """Detect trend direction from a window of candles."""
        if len(candles) < 2:
            return MarketRegime.TRANSITION

        first = float(candles[0].close)
        last = float(candles[-1].close)
        pct_change = (last - first) / first if first > 0 else 0.0

        if pct_change > self.trend_threshold:
            return MarketRegime.TRENDING_UP
        elif pct_change < -self.trend_threshold:
            return MarketRegime.TRENDING_DOWN
        return MarketRegime.RANGING

    def _detect_volatility(self, candles: Sequence[Candle], index: int) -> MarketRegime:
        """Detect volatility regime using rolling z-score."""
        window = min(self.vol_window, index + 1)
        recent = candles[max(0, index - window + 1) : index + 1]

        if len(recent) < 2:
            return MarketRegime.LOW_VOL

        # Calculate daily returns
        returns = []
        for i in range(1, len(recent)):
            o = float(recent[i - 1].close)
            c = float(recent[i].close)
            if o > 0:
                returns.append((c - o) / o)

        if not returns:
            return MarketRegime.LOW_VOL

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_ret = math.sqrt(variance) if variance > 0 else 0.0

        # Current candle return z-score
        current_return = (
            (float(candles[index].close) - float(candles[index].open)) / float(candles[index].open)
            if float(candles[index].open) > 0
            else 0.0
        )
        z_score = current_return / std_ret if std_ret > 0 else 0.0

        return MarketRegime.HIGH_VOL if abs(z_score) > self.vol_z_threshold else MarketRegime.LOW_VOL


# ---------------------------------------------------------------------------
# Per-regime evaluation
# ---------------------------------------------------------------------------


def evaluate_regime_performance(
    candles: Sequence[Candle],
    regimes: list[MarketRegime],
    trades: list,  # list of Trade or dict with exit_price, entry_price, pnl
) -> list[RegimePerformance]:
    """Evaluate strategy performance within each regime.

    Args:
        candles: Candle data
        regimes: Regime for each candle
        trades: Completed trades (must have entry_time and exit_time)

    Returns:
        List of RegimePerformance, one per detected regime
    """
    regime_perf: dict[MarketRegime, dict] = {}

    for regime in MarketRegime:
        regime_perf[regime] = {
            "candles": 0,
            "trades": [],
            "regime_candles": [],
        }

    # Count candles per regime
    for i, regime in enumerate(regimes):
        regime_perf[regime]["candles"] += 1
        regime_perf[regime]["regime_candles"].append(i)

    # Assign trades to regimes (trade enters during a regime)
    for trade in trades:
        # Determine entry regime
        if hasattr(trade, "entry_time"):
            entry_idx = _find_candle_index(candles, trade.entry_time)
            if 0 <= entry_idx < len(regimes):
                entry_regime = regimes[entry_idx]
                regime_perf[entry_regime]["trades"].append(trade)

    # Build results
    results = []
    for regime, data in regime_perf.items():
        trades_list = data["trades"]
        n_trades = len(trades_list)

        if n_trades == 0:
            results.append(
                RegimePerformance(
                    regime=regime,
                    n_candles=data["candles"],
                    n_trades=0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_dd=0.0,
                    win_rate=0.0,
                    avg_trade_pnl=0.0,
                )
            )
            continue

        pnls = [float(t.pnl) if hasattr(t, "pnl") else 0.0 for t in trades_list]
        win_rate = sum(1 for p in pnls if p > 0) / n_trades
        avg_pnl = sum(pnls) / n_trades
        total_return = (
            sum(pnls)
            / max(abs(float(trades_list[0].entry_price) if hasattr(trades_list[0], "entry_price") else 1.0), 1e-9)
            if pnls
            else 0.0
        )

        # Calculate Sharpe from trade returns
        if n_trades >= 2:
            mean_p = sum(pnls) / n_trades
            var_p = sum((p - mean_p) ** 2 for p in pnls) / (n_trades - 1)
            sharpe = mean_p / math.sqrt(var_p) * math.sqrt(365) if var_p > 0 else 0.0
        else:
            sharpe = 0.0

        results.append(
            RegimePerformance(
                regime=regime,
                n_candles=data["candles"],
                n_trades=n_trades,
                return_pct=total_return,
                sharpe=sharpe,
                max_dd=0.0,  # Simplified
                win_rate=win_rate,
                avg_trade_pnl=avg_pnl,
            )
        )

    return results


def detect_regimes(
    candles: Sequence[Candle],
    detector: RegimeDetector | None = None,
) -> list[MarketRegime]:
    """Convenience function to detect regimes for a candle sequence.

    Args:
        candles: Candle data
        detector: Optional RegimeDetector (creates default if None)

    Returns:
        List of regimes, one per candle
    """
    if detector is None:
        detector = RegimeDetector()
    return detector.detect_regimes(candles)


def _find_candle_index(candles: Sequence[Candle], timestamp) -> int:
    """Find the index of the candle closest to a timestamp."""
    for i, c in enumerate(candles):
        if hasattr(c, "open_time") and c.open_time == timestamp:
            return i
        if hasattr(c, "close_time") and c.close_time == timestamp:
            return i
    # Fallback: find closest
    if hasattr(candles[0], "open_time"):
        best = 0
        best_diff = abs(getattr(candles[0], "open_time") - timestamp)
        for i, c in enumerate(candles):
            diff = abs(getattr(c, "open_time") - timestamp)
            if diff < best_diff:
                best = i
                best_diff = diff
        return best
    return 0
