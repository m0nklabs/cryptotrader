#!/usr/bin/env python3
"""Manual integration test for WebSocket real-time candle updates.

This script starts the API server with WebSocket enabled and demonstrates
the real-time candle update flow.

Usage:
    python scripts/test_websocket_integration.py

Requirements:
    - DATABASE_URL must be set in environment
    - Bitfinex API must be accessible
    - At least one symbol/timeframe pair must exist in the database
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

# Add repo root to path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.market_data.bitfinex_websocket import BitfinexWebSocketManager, CandleUpdate
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def on_candle_update(update: CandleUpdate) -> None:
    """Callback when a candle update is received."""
    logger.info(
        f"Received candle update: {update.symbol} {update.timeframe} @ {update.candle.open_time} "
        f"O:{update.candle.open} H:{update.candle.high} L:{update.candle.low} C:{update.candle.close} "
        f"V:{update.candle.volume}"
    )


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL is required")
        return 1

    # Verify database connection
    try:
        stores = PostgresStores(config=PostgresConfig(database_url=database_url))
        logger.info("Database connection successful")
    except Exception as exc:
        logger.error(f"Failed to connect to database: {exc}")
        return 1

    # Create WebSocket manager
    ws_manager = BitfinexWebSocketManager(callback=on_candle_update)

    # Subscribe to some popular pairs
    test_pairs = [
        ("BTCUSD", "1m"),
        ("ETHUSD", "1m"),
    ]

    logger.info("Starting WebSocket manager...")
    ws_manager.start()

    # Wait a moment for connection
    time.sleep(2)

    logger.info("Subscribing to test pairs...")
    for symbol, timeframe in test_pairs:
        ws_manager.subscribe(symbol, timeframe)
        logger.info(f"Subscribed to {symbol} {timeframe}")

    logger.info("Listening for candle updates (press Ctrl+C to stop)...")
    logger.info("Note: It may take up to 1 minute to receive the first update (when a candle closes)")

    try:
        # Keep running until interrupted
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        ws_manager.stop()
        logger.info("WebSocket manager stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
