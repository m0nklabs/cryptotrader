# Backtesting Framework

This module provides a framework for backtesting trading strategies on historical data.

## Quick Start

### 1. Define a Strategy

Implement the `Strategy` protocol by creating a class with an `on_candle` method:

```python
from core.backtest.strategy import Strategy, Signal
from core.types import Candle

class MyStrategy:
    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        # Access computed indicators
        rsi = indicators.get('rsi')
        
        if rsi is None:
            return None
            
        # Generate signals based on your logic
        if rsi < 30:
            return Signal(side="BUY", strength=50)
        elif rsi > 70:
            return Signal(side="SELL", strength=50)
        else:
            return Signal(side="HOLD", strength=0)
```

### 2. Run a Backtest

Use the `BacktestEngine` to run your strategy on historical data:

```python
from datetime import datetime, timedelta, timezone
from core.backtest.engine import BacktestEngine
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores

# Setup database connection
config = PostgresConfig(database_url="postgresql://...")
store = PostgresStores(config=config)

# Create engine
engine = BacktestEngine(candle_store=store, initial_capital=10000.0)

# Load historical data
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=30)

candles = engine.load_candles(
    exchange="bitfinex",
    symbol="BTCUSD",
    timeframe="1h",
    start=start_time,
    end=end_time,
)

# Run backtest
strategy = MyStrategy()
result = engine.run(strategy=strategy, candles=candles)
```

### 3. Analyze Results

The `BacktestResult` contains:

```python
# Trading performance
print(f"Trades: {len(result.trades)}")
print(f"Win Rate: {result.win_rate * 100:.2f}%")
print(f"Profit Factor: {result.profit_factor:.2f}")

# Risk metrics
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown * 100:.2f}%")

# Equity progression
print(f"Initial: ${result.equity_curve[0]:,.2f}")
print(f"Final: ${result.equity_curve[-1]:,.2f}")
```

### 4. Export Results

```python
import json

output = {
    "metrics": {
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown": result.max_drawdown,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
    },
    "trades": [
        {
            "entry_price": float(t.entry_price),
            "exit_price": float(t.exit_price),
            "side": t.side,
            "pnl": float(t.pnl),
        }
        for t in result.trades
    ],
    "equity_curve": result.equity_curve,
}

with open("results.json", "w") as f:
    json.dump(output, f, indent=2)
```

## CLI Runner

A command-line script is available at `scripts/run_backtest.py`:

```bash
# Set database connection
export DATABASE_URL="postgresql://user:pass@host:port/dbname"

# Run backtest
python scripts/run_backtest.py
```

The script will:
- Load 30 days of BTCUSD 1h candles
- Run the built-in RSI strategy
- Display performance metrics
- Export results to `backtest_results.json`

## Performance Metrics

### Sharpe Ratio
Measures risk-adjusted returns. Higher is better.
- Formula: `(Mean Return - Risk Free Rate) / Std Dev * sqrt(252)`
- > 1.0: Good
- > 2.0: Very good
- > 3.0: Excellent

### Maximum Drawdown
Largest peak-to-trough decline in equity. Lower is better.
- Expressed as percentage (0.0 to 1.0)
- < 10%: Low risk
- 10-20%: Moderate risk
- > 20%: High risk

### Win Rate
Percentage of profitable trades.
- Formula: `Winning Trades / Total Trades`
- > 50%: Positive edge
- Note: High win rate doesn't guarantee profitability

### Profit Factor
Ratio of gross profit to gross loss. Must be > 1.0 to be profitable.
- Formula: `Total Gross Profit / Total Gross Loss`
- > 1.0: Profitable
- > 1.5: Good
- > 2.0: Excellent

## Built-in Strategies

### RSI Strategy

A simple RSI-based mean reversion strategy:

```python
from core.backtest.engine import RSIStrategy

strategy = RSIStrategy(oversold=30.0, overbought=70.0)
```

- Buys when RSI < 30 (oversold)
- Sells when RSI > 70 (overbought)
- Holds in neutral range (30-70)

## Testing

Run unit tests:
```bash
pytest tests/test_backtest.py -v
```

Run integration tests:
```bash
pytest tests/test_backtest_integration.py -v
```

## Architecture

- `strategy.py`: Protocol definition for strategies
- `metrics.py`: Performance calculation functions
- `engine.py`: Core backtesting simulation engine
- `scripts/run_backtest.py`: CLI runner script
