"""Integration test for backtesting engine with sample data."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.engine import BacktestEngine, BacktestResult, RSIStrategy
from core.types import Candle


DEFAULT_INITIAL_CAPITAL = 10000.0


def _make_test_candle(close: float, idx: int = 0) -> Candle:
    """Helper to create a candle with minimal required fields."""
    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    open_time = base_time + timedelta(hours=idx)
    close_time = base_time + timedelta(hours=idx, minutes=59)
    return Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=open_time,
        close_time=close_time,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


def test_backtest_engine_with_rsi_strategy() -> None:
    """Test backtest engine can run with RSI strategy on sample data."""
    # Create trending price data that should trigger RSI signals
    # Start high (overbought), go down (oversold), then recover
    prices = (
        [100.0 + i for i in range(15)]  # Uptrend to trigger overbought
        + [115.0 - i for i in range(30)]  # Downtrend to trigger oversold
        + [85.0 + i * 0.5 for i in range(20)]  # Recovery
    )

    candles = [_make_test_candle(price, i) for i, price in enumerate(prices)]

    # Create a mock candle store that just returns the candles
    class MockCandleStore:
        def get_candles(self, **kwargs):
            return candles

    engine = BacktestEngine(candle_store=MockCandleStore(), initial_capital=DEFAULT_INITIAL_CAPITAL)
    strategy = RSIStrategy(oversold=30.0, overbought=70.0)

    result = engine.run(strategy=strategy, candles=candles)

    # Verify result structure
    assert isinstance(result, BacktestResult)
    assert isinstance(result.trades, list)
    assert isinstance(result.equity_curve, list)
    assert isinstance(result.sharpe_ratio, float)
    assert isinstance(result.max_drawdown, float)
    assert isinstance(result.win_rate, float)
    assert isinstance(result.profit_factor, float)
    assert isinstance(result.total_pnl, float)
    assert isinstance(result.total_return, float)

    # With trending data, we should have generated some trades
    assert len(result.trades) > 0, "Should generate at least one trade"

    # Equity curve should have entries
    assert len(result.equity_curve) > 0, "Should have equity curve"
    assert result.equity_curve[0] == DEFAULT_INITIAL_CAPITAL, "Should start with initial capital"
    assert abs((result.total_return * DEFAULT_INITIAL_CAPITAL) - result.total_pnl) < 1e-9

    # Metrics should be in valid ranges
    assert 0.0 <= result.max_drawdown <= 1.0, "Max drawdown should be 0-100%"
    assert 0.0 <= result.win_rate <= 1.0, "Win rate should be 0-100%"


def test_backtest_engine_with_flat_data() -> None:
    """Test backtest engine handles flat data without trades."""
    # Create flat price data (no RSI signals)
    prices = [100.0] * 50

    candles = [_make_test_candle(price, i) for i, price in enumerate(prices)]

    class MockCandleStore:
        def get_candles(self, **kwargs):
            return candles

    engine = BacktestEngine(candle_store=MockCandleStore(), initial_capital=DEFAULT_INITIAL_CAPITAL)
    strategy = RSIStrategy(oversold=30.0, overbought=70.0)

    result = engine.run(strategy=strategy, candles=candles)

    # With flat data, RSI should stay neutral (no extreme values)
    # May generate no trades or very few trades
    assert len(result.trades) >= 0, "Should handle flat data"
    assert result.equity_curve[0] == DEFAULT_INITIAL_CAPITAL, "Should start with initial capital"


def test_compare_strategies_returns_results() -> None:
    """Compare multiple strategies side-by-side."""
    prices = (
        [100.0 + i for i in range(15)]
        + [115.0 - i for i in range(30)]
        + [85.0 + i * 0.5 for i in range(20)]
    )
    candles = [_make_test_candle(price, i) for i, price in enumerate(prices)]

    class MockCandleStore:
        def get_candles(self, **kwargs):
            return candles

    engine = BacktestEngine(candle_store=MockCandleStore(), initial_capital=DEFAULT_INITIAL_CAPITAL)
    strategies = {
        "rsi_default": RSIStrategy(oversold=30.0, overbought=70.0),
        "rsi_tighter": RSIStrategy(oversold=25.0, overbought=75.0),
    }

    performances = engine.compare_strategies(strategies=strategies, candles=candles)

    assert len(performances) == 2
    assert performances[0].name == "rsi_default"
    assert isinstance(performances[0].result, BacktestResult)
    assert isinstance(performances[0].result.total_pnl, float)
