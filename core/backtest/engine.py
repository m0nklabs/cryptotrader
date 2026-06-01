"""Backtesting engine for simulating strategies on historical data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from core.backtest.metrics import (
    Trade,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from core.backtest.strategy import Signal, Strategy
from core.indicators.rsi import compute_rsi
from core.persistence.interfaces import CandleStore
from core.risk.sizing import PositionSize, calculate_position_size
from core.types import Candle


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    trades: list[Trade]
    equity_curve: list[float]
    total_pnl: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float


@dataclass
class StrategyPerformance:
    """Performance summary for a single strategy."""

    name: str
    result: BacktestResult


class BacktestEngine:
    """Engine for backtesting strategies on historical data."""

    def __init__(
        self,
        candle_store: CandleStore | None,
        initial_capital: float = 10000.0,
        position_size_config: PositionSize | None = None,
    ):
        self.candle_store = candle_store
        self.initial_capital = initial_capital
        self.position_size_config = position_size_config

    def load_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]:
        """Load candles from database for date range."""
        if self.candle_store is None:
            raise ValueError("candle_store is required to load candles")

        return self.candle_store.get_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

    def _calculate_dynamic_size(
        self,
        entry_price: Decimal,
        equity: float,
        stop_loss_pct: float = 0.05,
    ) -> Decimal:
        """Calculate dynamic position size using the configured method.

        Uses Kelly criterion when method is 'kelly', fixed fractional otherwise.
        The stop loss percentage determines risk per unit.
        When no sizing config is provided, preserve the legacy fixed 1.0 unit size.
        """
        if self.position_size_config is None:
            return Decimal("1.0")

        portfolio_value = Decimal(str(equity))
        stop_loss_price = entry_price * Decimal(str(1 - stop_loss_pct))

        try:
            size = calculate_position_size(
                config=self.position_size_config,
                portfolio_value=portfolio_value,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
            )
            return max(size, Decimal("0.01"))  # floor at 0.01
        except (ValueError, ZeroDivisionError):
            return Decimal("1.0")  # fallback to fixed

    def run(
        self,
        strategy: Strategy,
        candles: Sequence[Candle],
        stop_loss_pct: float = 0.05,
    ) -> BacktestResult:
        """Run backtest simulation on historical data.

        Args:
            strategy: Strategy implementing on_candle protocol
            candles: Historical candle data
            stop_loss_pct: Stop loss percentage for position sizing (default 5%)

        Returns:
            BacktestResult with trades and performance metrics
        """
        trades: list[Trade] = []
        equity_curve: list[float] = [self.initial_capital]
        current_equity = self.initial_capital
        position = None  # None, 'LONG', or 'SHORT'
        entry_price = None

        for i, candle in enumerate(candles):
            # Calculate indicators
            indicators = {}
            if i >= 14:  # Need enough candles for RSI
                indicators["rsi"] = compute_rsi(candles[max(0, i - 100) : i + 1], period=14)

            # Get signal from strategy
            signal = strategy.on_candle(candle, indicators)

            # Process signal
            if signal and signal.side != "HOLD":
                if position is None:
                    # Enter position with dynamic sizing
                    dynamic_size = self._calculate_dynamic_size(
                        entry_price=candle.close,
                        equity=current_equity,
                        stop_loss_pct=stop_loss_pct,
                    )
                    position = "LONG" if signal.side == "BUY" else "SHORT"
                    entry_price = candle.close
                    # Store the size on the position for exit
                    if not hasattr(self, "_current_position_size"):
                        self._current_position_size = {}
                    self._current_position_size[id(self)] = dynamic_size
                else:
                    # Exit position if signal is opposite
                    should_exit = (position == "LONG" and signal.side == "SELL") or (
                        position == "SHORT" and signal.side == "BUY"
                    )

                    if should_exit and entry_price:
                        # Get dynamic size for this position
                        dynamic_size = self._current_position_size.get(id(self), Decimal("1.0"))

                        # Close position
                        trade_side = "BUY" if position == "LONG" else "SELL"
                        trade = Trade(
                            entry_price=entry_price,
                            exit_price=candle.close,
                            side=trade_side,
                            size=dynamic_size,
                        )
                        trades.append(trade)
                        current_equity += float(trade.pnl)

                        # Enter new position with fresh dynamic sizing
                        dynamic_size = self._calculate_dynamic_size(
                            entry_price=candle.close,
                            equity=current_equity,
                            stop_loss_pct=stop_loss_pct,
                        )
                        position = "LONG" if signal.side == "BUY" else "SHORT"
                        entry_price = candle.close
                        self._current_position_size[id(self)] = dynamic_size

            equity_curve.append(current_equity)

        # Calculate returns for Sharpe ratio
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                returns.append((equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1])

        # Calculate metrics
        sharpe = calculate_sharpe_ratio(returns)
        max_dd = calculate_max_drawdown(equity_curve)
        win_rate = calculate_win_rate(trades)
        profit_factor = calculate_profit_factor(trades)
        final_equity = equity_curve[-1] if equity_curve else self.initial_capital
        total_pnl = final_equity - self.initial_capital
        epsilon = 1e-9
        if abs(self.initial_capital) < epsilon:
            total_return = 0.0
        else:
            total_return = total_pnl / self.initial_capital

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            total_pnl=total_pnl,
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
        )

    def compare_strategies(
        self, strategies: dict[str, Strategy], candles: Sequence[Candle]
    ) -> list[StrategyPerformance]:
        """Run multiple strategies side-by-side on the same candles."""
        performances: list[StrategyPerformance] = []
        for name, strategy in strategies.items():
            # Reset position size map for each strategy comparison
            if hasattr(self, "_current_position_size"):
                self._current_position_size = {}
            result = self.run(strategy=strategy, candles=candles)
            performances.append(StrategyPerformance(name=name, result=result))
        return performances


class RSIStrategy:
    """Example RSI-based strategy for backtesting."""

    def __init__(self, oversold: float = 30.0, overbought: float = 70.0):
        self.oversold = oversold
        self.overbought = overbought

    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        """Generate signal based on RSI indicator."""
        if "rsi" not in indicators:
            return None

        rsi = indicators["rsi"]

        if rsi < self.oversold:
            return Signal(side="BUY", strength=int((self.oversold - rsi) * 3))
        elif rsi > self.overbought:
            return Signal(side="SELL", strength=int((rsi - self.overbought) * 3))
        else:
            return Signal(side="HOLD", strength=0)
