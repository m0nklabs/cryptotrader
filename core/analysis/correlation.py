"""Asset Correlation Calculator

Calculate rolling correlation between crypto assets for portfolio diversification analysis.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from core.storage.postgres.stores import PostgresStores

logger = logging.getLogger(__name__)


async def calculate_correlation_matrix(
    stores: PostgresStores,
    symbols: list[str],
    exchange: str = "bitfinex",
    timeframe: str = "1d",
    lookback_days: int = 30,
) -> dict[str, Any]:
    """Calculate correlation matrix between assets.

    Args:
        stores: Database stores
        symbols: List of trading symbols (e.g., ["BTCUSD", "ETHUSD"])
        exchange: Exchange name
        timeframe: Timeframe for analysis
        lookback_days: Number of days to look back (7, 30, 90, 365)

    Returns:
        Dictionary with correlation matrix and metadata:
        {
            "symbols": ["BTC", "ETH", ...],
            "matrix": [[1.0, 0.8, ...], [0.8, 1.0, ...], ...],
            "lookback_days": 30,
            "data_points": 30,
            "start_time": <timestamp>,
            "end_time": <timestamp>
        }
    """
    if len(symbols) < 2:
        raise ValueError("Need at least 2 symbols for correlation analysis")

    # Fetch OHLCV data for all symbols
    all_data: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        try:
            async with stores.pool.acquire() as conn:
                result = await conn.fetch(
                    """
                    SELECT open_time, close
                    FROM candles
                    WHERE exchange = $1 AND symbol = $2 AND timeframe = $3
                      AND open_time >= NOW() - INTERVAL '1 day' * $4
                    ORDER BY open_time ASC
                    """,
                    exchange,
                    symbol,
                    timeframe,
                    lookback_days,
                )

                if not result:
                    logger.warning(f"No data found for {symbol}")
                    continue

                df = pd.DataFrame(
                    [(row["open_time"], float(row["close"])) for row in result],
                    columns=["time", "close"],
                )
                df["time"] = pd.to_datetime(df["time"], utc=True)
                df = df.set_index("time")
                all_data[symbol] = df

        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            continue

    if len(all_data) < 2:
        raise ValueError(f"Insufficient data: only {len(all_data)} symbols have data")

    # Align all dataframes by time (inner join)
    combined = pd.DataFrame()
    for symbol, df in all_data.items():
        # Extract base asset (e.g., BTC from BTCUSD or BTCUSDT)
        # Handle common quote currencies (longest first to avoid partial matches)
        base = symbol
        for quote in ['USDT', 'USDC', 'USD', 'EUR']:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                break
        # Only if no quote currency matched, it's likely a base pair like 'BTC'
        combined[base] = df["close"]

    # Drop NaN values
    combined = combined.dropna()

    if combined.empty or len(combined) < 2:
        raise ValueError("Insufficient overlapping data points")

    # Calculate Pearson correlation
    corr_matrix = combined.corr()

    # Convert to list of lists for JSON serialization
    matrix = corr_matrix.values.tolist()
    symbol_names = corr_matrix.columns.tolist()

    # Metadata
    start_time = combined.index.min().isoformat() if not combined.empty else None
    end_time = combined.index.max().isoformat() if not combined.empty else None

    return {
        "symbols": symbol_names,
        "matrix": matrix,
        "lookback_days": lookback_days,
        "data_points": len(combined),
        "start_time": start_time,
        "end_time": end_time,
    }
