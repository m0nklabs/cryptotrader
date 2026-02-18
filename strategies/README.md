# Trading Strategies

This directory contains example trading strategies for backtesting.

## Available Strategies

### RSI Mean Reversion (`rsi_mean_reversion.py`)

A simple RSI-based mean reversion strategy that:
- **Buys** when RSI falls below the oversold threshold (default: 30)
- **Sells** when RSI rises above the overbought threshold (default: 70)
- **Holds** in the neutral zone (between thresholds)

**Parameters:**
- `oversold`: RSI level for buy signals (default: 30.0)
- `overbought`: RSI level for sell signals (default: 70.0)

**Use case:** Best for ranging markets where assets tend to mean-revert.

---

### SMA Crossover (`sma_crossover.py`)

A trend-following strategy using two Simple Moving Averages:
- **Buys** when fast SMA crosses above slow SMA (golden cross)
- **Sells** when fast SMA crosses below slow SMA (death cross)
- **Holds** when no crossover is detected

**Parameters:**
- `fast_period`: Period for fast SMA (default: 10)
- `slow_period`: Period for slow SMA (default: 30)

**Use case:** Best for trending markets with clear directional moves.

---

## Creating Custom Strategies

To create a custom strategy:

1. Create a new file in this directory (e.g., `my_strategy.py`)
2. Implement the `on_candle` method following the `Strategy` protocol:

```python
from core.backtest.strategy import Signal
from core.types import Candle

class MyStrategy:
    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        """Process candle and return trading signal.

        Args:
            candle: Current OHLCV candle
            indicators: Pre-computed indicators (e.g., {'rsi': 45.2})

        Returns:
            Signal with side ('BUY', 'SELL', 'HOLD') or None
        """
        # Your logic here
        return Signal(side="HOLD", strength=0)
```

3. Add your strategy to `__init__.py`
4. Register it in `api/routes/backtest.py` for API access

## Testing Strategies

Run strategy tests:
```bash
pytest tests/test_strategies.py -v
```

Run a backtest via API:
```bash
curl -X POST http://localhost:8000/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD",
    "strategy": "rsi",
    "initial_capital": 10000
  }'
```

## Best Practices

1. **Keep it simple**: Start with simple logic, add complexity only when needed
2. **Test thoroughly**: Use historical data across different market conditions
3. **Risk management**: Consider position sizing and stop losses
4. **Avoid overfitting**: Don't optimize too much on historical data
5. **Paper trade first**: Always validate with paper trading before going live
