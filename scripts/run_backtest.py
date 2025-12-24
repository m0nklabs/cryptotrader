#!/usr/bin/env python
"""CLI runner for backtesting strategies."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.engine import BacktestEngine, RSIStrategy
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores


def export_results_json(result, filename: str) -> None:
    """Export backtest results to JSON file."""
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

    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Results exported to {filename}")


def main() -> None:
    """Run backtest on BTCUSD 1h for 30 days."""
    # Setup database connection
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL environment variable is required")
        print("Please set DATABASE_URL to your PostgreSQL connection string")
        sys.exit(1)

    config = PostgresConfig(database_url=database_url)
    store = PostgresStores(config=config)
    print("Using PostgreSQL store")

    # Configure backtest
    exchange = "bitfinex"
    symbol = "BTCUSD"
    timeframe = "1h"
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=30)

    print("\nBacktest Configuration:")
    print(f"  Symbol: {symbol}")
    print(f"  Exchange: {exchange}")
    print(f"  Timeframe: {timeframe}")
    print(f"  Start: {start_time.isoformat()}")
    print(f"  End: {end_time.isoformat()}")

    # Load candles
    print("\nLoading candles...")
    engine = BacktestEngine(candle_store=store, initial_capital=10000.0)
    candles = engine.load_candles(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        start=start_time,
        end=end_time,
    )

    print(f"Loaded {len(candles)} candles")

    if len(candles) == 0:
        print("ERROR: No candles found. Please backfill data first.")
        sys.exit(1)

    # Run backtest
    print("\nRunning backtest with RSI strategy...")
    strategy = RSIStrategy(oversold=30.0, overbought=70.0)
    result = engine.run(strategy=strategy, candles=candles)

    # Display results
    print(f"\n{'=' * 50}")
    print("BACKTEST RESULTS")
    print(f"{'=' * 50}")
    print(f"Trades: {len(result.trades)}")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {result.max_drawdown * 100:.2f}%")
    print(f"Win Rate: {result.win_rate * 100:.2f}%")
    print(f"Profit Factor: {result.profit_factor:.2f}")

    if result.equity_curve:
        final_equity = result.equity_curve[-1]
        total_return = ((final_equity - 10000.0) / 10000.0) * 100
        print("Initial Capital: $10,000.00")
        print(f"Final Equity: ${final_equity:,.2f}")
        print(f"Total Return: {total_return:.2f}%")

    # Export to JSON
    output_file = "backtest_results.json"
    export_results_json(result, output_file)

    print(f"\n{'=' * 50}")


if __name__ == "__main__":
    main()
