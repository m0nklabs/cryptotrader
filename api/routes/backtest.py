"""Backtest API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.backtest.engine import BacktestEngine
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores

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
            raise RuntimeError("DATABASE_URL environment variable not set")
        config = PostgresConfig(database_url=database_url)
        _stores = PostgresStores(config=config)
    return _stores


# ============ Request/Response Models ============


class BacktestRequest(BaseModel):
    """Request to run a backtest."""

    exchange: str = Field("bitfinex", description="Exchange name")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSD)")
    timeframe: str = Field("1h", description="Candle timeframe (e.g., 1m, 1h, 1d)")
    strategy: Literal["rsi"] = Field("rsi", description="Strategy to backtest")
    start_date: Optional[str] = Field(None, description="Start date (ISO format, defaults to 30 days ago)")
    end_date: Optional[str] = Field(None, description="End date (ISO format, defaults to now)")
    initial_capital: float = Field(10000.0, gt=0, description="Initial capital for backtest")

    # Strategy-specific parameters
    rsi_oversold: Optional[float] = Field(30.0, ge=0, le=100, description="RSI oversold threshold")
    rsi_overbought: Optional[float] = Field(70.0, ge=0, le=100, description="RSI overbought threshold")


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


# ============ Endpoints ============


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest) -> dict[str, Any]:
    """Run a backtest on historical data.

    Args:
        request: Backtest configuration including symbol, strategy, and date range.

    Returns:
        Backtest results with performance metrics and trade history.

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

        # Create backtest engine
        engine = BacktestEngine(candle_store=stores, initial_capital=request.initial_capital)

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
            from core.backtest.engine import RSIStrategy

            strategy = RSIStrategy(
                oversold=request.rsi_oversold or 30.0,
                overbought=request.rsi_overbought or 70.0,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_strategy", "message": f"Unknown strategy: {request.strategy}"},
            )

        # Run backtest
        result = engine.run(strategy=strategy, candles=candles)

        # Convert to response
        return {
            "exchange": request.exchange,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "strategy": request.strategy,
            "start_date": start_time.isoformat(),
            "end_date": end_time.isoformat(),
            "initial_capital": request.initial_capital,
            "total_pnl": result.total_pnl,
            "total_return": result.total_return,
            "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "num_trades": len(result.trades),
            "trades": [
                {
                    "entry_price": str(t.entry_price),
                    "exit_price": str(t.exit_price),
                    "side": t.side,
                    "size": str(t.size),
                    "pnl": str(t.pnl),
                }
                for t in result.trades
            ],
            "equity_curve": result.equity_curve,
        }

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
    ]
