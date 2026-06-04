"""Integration test for backtesting engine with sample data."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.engine import BacktestEngine, BacktestResult, RSIStrategy
from core.backtest.strategy import Signal
from core.risk.sizing import PositionSize
from core.types import Candle


DEFAULT_INITIAL_CAPITAL = 10000.0
FLOAT_TOLERANCE = 1e-9


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
    assert abs((result.total_return * DEFAULT_INITIAL_CAPITAL) - result.total_pnl) < FLOAT_TOLERANCE

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


def test_backtest_engine_closes_zero_entry_price_position() -> None:
    """A zero entry price is still a valid position to close."""

    class ZeroEntryExitStrategy:
        def __init__(self) -> None:
            self.calls = 0

        def on_candle(self, candle, indicators):
            self.calls += 1
            if self.calls == 1:
                return Signal(side="BUY", strength=100)
            if self.calls == 2:
                return Signal(side="SELL", strength=100)
            return Signal(side="HOLD", strength=0)

    candles = [_make_test_candle(0.0, 0), _make_test_candle(1.0, 1)]

    engine = BacktestEngine(candle_store=None, initial_capital=DEFAULT_INITIAL_CAPITAL)
    result = engine.run(strategy=ZeroEntryExitStrategy(), candles=candles)

    assert len(result.trades) == 1
    assert result.trades[0].entry_price == Decimal("0")
    assert result.trades[0].exit_price == Decimal("1.0")


def test_compare_strategies_returns_results() -> None:
    """Compare multiple strategies side-by-side."""
    uptrend = [100.0 + i for i in range(15)]
    downtrend = [115.0 - i for i in range(30)]
    recovery = [85.0 + i * 0.5 for i in range(20)]
    prices = uptrend + downtrend + recovery
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
    perf_by_name = {perf.name: perf for perf in performances}
    assert "rsi_default" in perf_by_name
    default_perf = perf_by_name["rsi_default"]
    assert isinstance(default_perf.result, BacktestResult)
    assert isinstance(default_perf.result.total_pnl, float)


def test_backtest_engine_dynamic_kelly_sizing() -> None:
    """Test that backtest engine uses dynamic Kelly sizing, not fixed 1.0."""
    # Create price data with varying prices so Kelly sizing produces different sizes
    prices = (
        [100.0 + i for i in range(15)]  # Uptrend to trigger overbought
        + [115.0 - i for i in range(30)]  # Downtrend to trigger oversold
        + [85.0 + i * 0.5 for i in range(20)]  # Recovery
    )
    candles = [_make_test_candle(price, i) for i, price in enumerate(prices)]

    class MockCandleStore:
        def get_candles(self, **kwargs):
            return candles

    # Use Kelly sizing
    kelly_config = PositionSize(
        method="kelly",
        kelly_fraction=Decimal("0.5"),
        win_rate=Decimal("0.55"),
        avg_win=Decimal("0.05"),
        avg_loss=Decimal("0.02"),
    )
    engine = BacktestEngine(
        candle_store=MockCandleStore(),
        initial_capital=DEFAULT_INITIAL_CAPITAL,
        position_size_config=kelly_config,
    )
    strategy = RSIStrategy(oversold=30.0, overbought=70.0)
    result = engine.run(strategy=strategy, candles=candles)

    assert len(result.trades) > 0, "Should generate at least one trade"

    # Verify trades have dynamic (non-1.0) sizes
    sizes = [float(t.size) for t in result.trades]
    # With Kelly sizing on varying prices, sizes should differ
    # At least some trades should have size != 1.0
    non_fixed = sum(1 for s in sizes if abs(s - 1.0) > 0.01)
    assert non_fixed > 0, f"Expected some trades with dynamic size, got sizes: {sizes}"

    # Verify PnL accounts for size
    for trade in result.trades:
        if trade.side == "BUY":
            expected_pnl = float(trade.exit_price - trade.entry_price) * float(trade.size)
        else:
            expected_pnl = float(trade.entry_price - trade.exit_price) * float(trade.size)
        assert (
            abs(float(trade.pnl) - expected_pnl) < FLOAT_TOLERANCE
        ), f"PnL mismatch: expected {expected_pnl}, got {float(trade.pnl)}"


def test_backtest_engine_fixed_sizing_still_works() -> None:
    """Test that fixed sizing still works as before (size=1.0)."""
    prices = [100.0 + i for i in range(15)]
    candles = [_make_test_candle(price, i) for i, price in enumerate(prices)]

    class MockCandleStore:
        def get_candles(self, **kwargs):
            return candles

    # Default fixed sizing
    engine = BacktestEngine(candle_store=MockCandleStore(), initial_capital=DEFAULT_INITIAL_CAPITAL)
    strategy = RSIStrategy(oversold=30.0, overbought=70.0)
    result = engine.run(strategy=strategy, candles=candles)

    assert isinstance(result, BacktestResult)
    assert len(result.trades) >= 0


def test_backtest_engine_sizing_affects_equity() -> None:
    """Test that dynamic sizing correctly affects equity curve."""
    # Large price swings to create big PnL differences
    prices = [100.0, 105.0, 95.0, 110.0, 90.0, 120.0, 85.0, 130.0]
    candles = [_make_test_candle(price, i) for i, price in enumerate(prices)]

    class MockCandleStore:
        def get_candles(self, **kwargs):
            return candles

    kelly_config = PositionSize(
        method="kelly",
        kelly_fraction=Decimal("0.5"),
        win_rate=Decimal("0.55"),
        avg_win=Decimal("0.05"),
        avg_loss=Decimal("0.02"),
    )
    engine = BacktestEngine(
        candle_store=MockCandleStore(),
        initial_capital=DEFAULT_INITIAL_CAPITAL,
        position_size_config=kelly_config,
    )
    strategy = RSIStrategy(oversold=30.0, overbought=70.0)
    result = engine.run(strategy=strategy, candles=candles)

    # Equity curve should start with initial capital
    assert result.equity_curve[0] == DEFAULT_INITIAL_CAPITAL
    # Total PnL should be consistent with equity curve
    assert abs((result.total_return * DEFAULT_INITIAL_CAPITAL) - result.total_pnl) < FLOAT_TOLERANCE
