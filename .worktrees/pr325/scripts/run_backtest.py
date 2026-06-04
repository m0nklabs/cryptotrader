#!/usr/bin/env python
"""CLI runner for backtesting strategies."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.engine import (
    BacktestEngine,
    BacktestResult,
    RSIStrategy,
    StrategyPerformance,
)
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores
from core.strategy_eval.cost_aware import (
    evaluate_cost_aware,
    to_dict as cost_aware_to_dict,
)
from core.strategy_eval.kelly_comparison import (
    run_kelly_backtest,
)
from core.strategy_eval.regime import RegimeDetector


def _serialize_result(result: BacktestResult) -> dict:
    """Serialize a BacktestResult to a dictionary for export."""
    return {
        "metrics": {
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "total_pnl": result.total_pnl,
            "total_return": result.total_return,
            "final_equity": result.equity_curve[-1] if len(result.equity_curve) > 0 else None,
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


def export_results_json(
    result: BacktestResult | list[StrategyPerformance],
    filename: str,
    candles=None,
    regime_detector=None,
) -> None:
    """Export backtest results (single or comparison) to JSON file.

    Includes cost-adjusted metrics, regime breakdowns, and Kelly sizing
    comparison (half-Kelly 0.5 vs full-Kelly 1.0).
    """
    if isinstance(result, list):
        output = {"strategies": []}
        for perf in result:
            strategy_data = {"name": perf.name, **_serialize_result(perf.result)}

            # Add cost-aware evaluation if candles available
            if candles is not None:
                cost_eval = evaluate_cost_aware(perf.result, candles, regime_detector=regime_detector)
                strategy_data["cost_adjusted"] = cost_aware_to_dict(cost_eval)

            # Add Kelly sizing comparison
            kelly_comp = run_kelly_backtest(perf.result)
            strategy_data["kelly_sizing"] = kelly_comp.to_dict()

            output["strategies"].append(strategy_data)
    else:
        output = _serialize_result(result)

        # Add cost-aware evaluation if candles available
        if candles is not None:
            cost_eval = evaluate_cost_aware(result, candles, regime_detector=regime_detector)
            output["cost_adjusted"] = cost_aware_to_dict(cost_eval)

        # Add Kelly sizing comparison
        kelly_comp = run_kelly_backtest(result)
        output["kelly_sizing"] = kelly_comp.to_dict()

    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Results exported to {filename}")


def main() -> None:
    """Run backtest on BTCUSD 1h for 30 days."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run backtesting on historical data")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial capital (default: 10000.0)")
    parser.add_argument("--symbol", type=str, default="BTCUSD", help="Trading symbol (default: BTCUSD)")
    parser.add_argument("--exchange", type=str, default="bitfinex", help="Exchange (default: bitfinex)")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (default: 1h)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backtest (default: 30)")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run multiple strategy variants side-by-side for comparison",
    )
    args = parser.parse_args()

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
    exchange = args.exchange
    symbol = args.symbol
    timeframe = args.timeframe
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=args.days)

    print("\nBacktest Configuration:")
    print(f"  Symbol: {symbol}")
    print(f"  Exchange: {exchange}")
    print(f"  Timeframe: {timeframe}")
    print(f"  Start: {start_time.isoformat()}")
    print(f"  End: {end_time.isoformat()}")
    print(f"  Initial Capital: ${args.capital:,.2f}")

    # Load candles
    print("\nLoading candles...")
    engine = BacktestEngine(candle_store=store, initial_capital=args.capital)
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
    base_strategy = RSIStrategy(oversold=30.0, overbought=70.0)
    regime_detector = RegimeDetector()

    if args.compare:
        strategies = {
            "rsi_default": base_strategy,
            "rsi_tighter": RSIStrategy(oversold=25.0, overbought=75.0),
            "rsi_conservative": RSIStrategy(oversold=35.0, overbought=65.0),
        }
        performances = engine.compare_strategies(strategies=strategies, candles=candles)

        print(f"\n{'=' * 80}")
        print("STRATEGY COMPARISON")
        print(f"{'=' * 80}")
        header = (
            f"{'Strategy':<18}{'Trades':>8}{'Sharpe':>10}{'MaxDD%':>10}{'Win%':>10}{'PF':>8}{'PnL':>12}{'Return%':>12}"
        )
        print(header)
        print("-" * len(header))
        for perf in performances:
            res = perf.result
            final_equity = res.equity_curve[-1] if res.equity_curve else args.capital + res.total_pnl
            print(
                f"{perf.name:<18}"
                f"{len(res.trades):>8}"
                f"{res.sharpe_ratio:>10.2f}"
                f"{(res.max_drawdown * 100):>10.2f}"
                f"{(res.win_rate * 100):>10.2f}"
                f"{res.profit_factor:>8.2f}"
                f"{res.total_pnl:>12.2f}"
                f"{(res.total_return * 100):>12.2f}"
            )
            print(f"   Final Equity: ${final_equity:,.2f}")

        output_file = "backtest_comparison.json"
        export_results_json(performances, output_file, candles=candles, regime_detector=regime_detector)
    else:
        result = engine.run(strategy=base_strategy, candles=candles)

        # Display results
        print(f"\n{'=' * 50}")
        print("BACKTEST RESULTS")
        print(f"{'=' * 50}")
        print(f"Trades: {len(result.trades)}")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {result.max_drawdown * 100:.2f}%")
        print(f"Win Rate: {result.win_rate * 100:.2f}%")
        print(f"Profit Factor: {result.profit_factor:.2f}")
        print(f"Total PnL: ${result.total_pnl:,.2f}")
        print(f"Total Return: {result.total_return * 100:.2f}%")

        if result.equity_curve:
            final_equity = result.equity_curve[-1]
            print(f"Initial Capital: ${args.capital:,.2f}")
            print(f"Final Equity: ${final_equity:,.2f}")

        # Export to JSON with cost-aware evaluation
        output_file = "backtest_results.json"
        export_results_json(result, output_file, candles=candles, regime_detector=regime_detector)

    print(f"\n{'=' * 50}")


if __name__ == "__main__":
    main()
