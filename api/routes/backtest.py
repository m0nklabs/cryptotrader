"""Backtest API endpoints."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.backtest.engine import BacktestEngine
from core.fees.model import FeeModel
from core.risk.sizing import PositionSize
from core.strategy_eval.walk_forward import (
    WalkForwardConfig,
    run_walk_forward,
)
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

# Global stores instance (lazy init)
_stores: PostgresStores | None = None


def _get_stores() -> PostgresStores:
    """Get or initialize the PostgresStores instance."""
    global _stores
    if _stores is None:
        import os

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL is not set")
        config = PostgresConfig(database_url=database_url)
        _stores = PostgresStores(config=config)
    return _stores


def _write_comparison_json(data: dict[str, Any]) -> None:
    """Write combined backtest + walk-forward results to backtest_comparison.json."""
    output_dir = Path(os.getenv("BACKTEST_OUTPUT_DIR", "/tmp"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "backtest_comparison.json"

    # Append to file if it exists (preserve history)
    existing = []
    if output_path.exists():
        try:
            with open(output_path, "r") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = [existing]
        except (json.JSONDecodeError, OSError):
            existing = []

    existing.append(data)

    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2, default=str)

    logger.info("Wrote comparison results to %s (total entries: %d)", output_path, len(existing))


# ============ Request/Response Models ============


class BacktestRequest(BaseModel):
    """Request to run a backtest."""

    exchange: str = Field("bitfinex", description="Exchange name")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSD)")
    timeframe: str = Field("1h", description="Candle timeframe (e.g., 1m, 1h, 1d)")
    strategy: Literal["rsi", "sma"] = Field("rsi", description="Strategy to backtest")
    start_date: Optional[str] = Field(None, description="Start date (ISO format, defaults to 30 days ago)")
    end_date: Optional[str] = Field(None, description="End date (ISO format, defaults to now)")
    initial_capital: float = Field(10000.0, gt=0, description="Initial capital for backtest")

    # Strategy-specific parameters
    rsi_oversold: Optional[float] = Field(30.0, ge=0, le=100, description="RSI oversold threshold")
    rsi_overbought: Optional[float] = Field(70.0, ge=0, le=100, description="RSI overbought threshold")
    sma_fast_period: Optional[int] = Field(10, ge=1, description="SMA fast period")
    sma_slow_period: Optional[int] = Field(30, ge=1, description="SMA slow period")


class TradeResponse(BaseModel):
    """A single trade in the backtest."""

    entry_price: str
    exit_price: str
    side: str
    size: str
    pnl: str


class BacktestResponse(BaseModel):
    """Backtest results response."""

    # Metadata
    exchange: str
    symbol: str
    timeframe: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float

    # Performance metrics
    total_pnl: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float

    # Trade details
    num_trades: int
    trades: list[TradeResponse]
    equity_curve: list[float]


class StrategyInfo(BaseModel):
    """Information about an available strategy."""

    name: str
    description: str
    parameters: dict[str, Any]


class WalkForwardFoldResponse(BaseModel):
    """One fold in the walk-forward evaluation."""

    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_return: float
    test_return: float
    test_sharpe: float
    test_max_dd: float
    test_win_rate: float
    test_trades: int
    oos_decay: float
    oos_trades: list[dict] = Field(default_factory=list)
    oos_returns: list[float] = Field(default_factory=list)


class WalkForwardResponse(BaseModel):
    """Aggregated walk-forward results."""

    n_folds: int
    mean_train_return: float
    mean_test_return: float
    mean_oos_decay: float
    in_sample_consistency: float
    oos_significant: bool
    oos_sharpe: float
    oos_max_dd: float
    oos_win_rate: float
    overfitting_risk: str
    oos_trades: list[dict] = Field(default_factory=list)
    oos_returns: list[float] = Field(default_factory=list)
    total_oos_trades: int = 0
    folds: list[WalkForwardFoldResponse]


class BacktestComparisonResponse(BaseModel):
    """Combined backtest + walk-forward results."""

    # Standard backtest
    exchange: str
    symbol: str
    timeframe: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    total_pnl: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    num_trades: int
    trades: list[TradeResponse]
    equity_curve: list[float]

    # Walk-forward results
    walk_forward: WalkForwardResponse


# ============ Endpoints ============


@router.post("/run", response_model=BacktestComparisonResponse)
async def run_backtest(request: BacktestRequest) -> dict[str, Any]:
    """Run a backtest on historical data with walk-forward validation.

    Args:
        request: Backtest configuration including symbol, strategy, and date range.

    Returns:
        Combined backtest results with standard metrics and walk-forward validation.

    Raises:
        HTTPException: If insufficient data or invalid parameters.
    """
    try:
        stores = _get_stores()

        # Parse dates
        if request.end_date:
            end_time = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))
        else:
            end_time = datetime.now(timezone.utc)

        if request.start_date:
            start_time = datetime.fromisoformat(request.start_date.replace("Z", "+00:00"))
        else:
            start_time = end_time - timedelta(days=30)

        # Create backtest engine with Kelly sizing
        kelly_position_config = PositionSize(
            method="kelly",
            kelly_fraction=Decimal("0.5"),
            win_rate=Decimal("0.55"),
            avg_win=Decimal("0.05"),
            avg_loss=Decimal("0.02"),
        )
        engine = BacktestEngine(
            candle_store=stores,
            initial_capital=request.initial_capital,
            position_size_config=kelly_position_config,
        )

        # Load candles
        candles = engine.load_candles(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            start=start_time,
            end=end_time,
        )

        if not candles:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "no_data",
                    "message": f"No candles found for {request.symbol} on {request.exchange}",
                },
            )

        # Select and configure strategy
        if request.strategy == "rsi":
            from strategies.rsi_mean_reversion import RSIMeanReversionStrategy

            strategy = RSIMeanReversionStrategy(
                oversold=request.rsi_oversold or 30.0,
                overbought=request.rsi_overbought or 70.0,
            )
        elif request.strategy == "sma":
            from strategies.sma_crossover import SMACrossoverStrategy

            strategy = SMACrossoverStrategy(
                fast_period=request.sma_fast_period or 10,
                slow_period=request.sma_slow_period or 30,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_strategy", "message": f"Unknown strategy: {request.strategy}"},
            )

        # Run standard backtest
        result = engine.run(strategy=strategy, candles=candles)

        # Generate comprehensive report
        from core.backtest.report import generate_report, report_to_dict

        report = generate_report(
            strategy_name=request.strategy,
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_time,
            end_date=end_time,
            initial_capital=request.initial_capital,
            result=result,
        )

        # Convert to response dict and rename strategy_name to strategy
        response_dict = report_to_dict(report)
        response_dict["strategy"] = response_dict.pop("strategy_name")

        # Run walk-forward validation
        fee_model = FeeModel()
        wf_config = WalkForwardConfig(
            train_size_days=90,
            test_size_days=30,
            step_size_days=15,
            lookback_candles=200,
        )
        wf_result = run_walk_forward(
            strategy=strategy,
            candles=candles,
            config=wf_config,
            fee_model=fee_model,
            position_size_config=kelly_position_config,
        )

        # Convert walk-forward result for response
        wf_response = WalkForwardResponse(
            n_folds=wf_result.n_folds,
            mean_train_return=wf_result.mean_train_return,
            mean_test_return=wf_result.mean_test_return,
            mean_oos_decay=wf_result.mean_oos_decay,
            in_sample_consistency=wf_result.in_sample_consistency,
            oos_significant=wf_result.oos_significant,
            oos_sharpe=wf_result.oos_sharpe,
            oos_max_dd=wf_result.oos_max_dd,
            oos_win_rate=wf_result.oos_win_rate,
            overfitting_risk=wf_result.overfitting_risk,
            oos_trades=wf_result.oos_trades,
            oos_returns=wf_result.oos_returns,
            total_oos_trades=wf_result.total_oos_trades,
            folds=[
                WalkForwardFoldResponse(
                    train_start=f.train_start.isoformat(),
                    train_end=f.train_end.isoformat(),
                    test_start=f.test_start.isoformat(),
                    test_end=f.test_end.isoformat(),
                    train_return=f.train_return,
                    test_return=f.test_return,
                    test_sharpe=f.test_sharpe,
                    test_max_dd=f.test_max_dd,
                    test_win_rate=f.test_win_rate,
                    test_trades=f.test_trades,
                    oos_decay=f.oos_decay,
                    oos_trades=f.oos_trades,
                    oos_returns=f.oos_returns,
                )
                for f in wf_result.folds
            ],
        )

        # Combine results
        combined = {**response_dict, "walk_forward": wf_response.model_dump()}

        # Write to backtest_comparison.json
        _write_comparison_json(combined)

        # Log walk-forward results
        logger.info(
            "Walk-forward: %d folds, mean train=%.4f, mean test=%.4f, OOS decay=%.4f, overfitting=%s, significant=%s",
            wf_result.n_folds,
            wf_result.mean_train_return,
            wf_result.mean_test_return,
            wf_result.mean_oos_decay,
            wf_result.overfitting_risk,
            wf_result.oos_significant,
        )

        return combined

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "backtest_failed", "message": str(e)},
        ) from e


@router.get("/strategies", response_model=list[StrategyInfo])
async def list_strategies() -> list[dict[str, Any]]:
    """List available backtest strategies.

    Returns:
        List of strategy information including name, description, and parameters.
    """
    return [
        {
            "name": "rsi",
            "description": "RSI mean reversion strategy - buys when RSI < oversold, sells when RSI > overbought",
            "parameters": {
                "rsi_oversold": {
                    "type": "float",
                    "default": 30.0,
                    "min": 0.0,
                    "max": 100.0,
                    "description": "RSI oversold threshold (buy signal)",
                },
                "rsi_overbought": {
                    "type": "float",
                    "default": 70.0,
                    "min": 0.0,
                    "max": 100.0,
                    "description": "RSI overbought threshold (sell signal)",
                },
            },
        },
        {
            "name": "sma",
            "description": "SMA crossover strategy - buys on golden cross (fast SMA > slow SMA), sells on death cross",
            "parameters": {
                "sma_fast_period": {
                    "type": "int",
                    "default": 10,
                    "min": 1,
                    "description": "Fast SMA period",
                },
                "sma_slow_period": {
                    "type": "int",
                    "default": 30,
                    "min": 1,
                    "description": "Slow SMA period (must be > fast period)",
                },
            },
        },
    ]
