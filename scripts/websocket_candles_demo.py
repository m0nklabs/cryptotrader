#!/usr/bin/env python3
"""
WebSocket Candle Streaming Demo
================================

Demonstrates real-time candle updates using Bitfinex WebSocket API.

Usage:
    python scripts/websocket_candles_demo.py
    python scripts/websocket_candles_demo.py --symbol ETHUSD --timeframe 5m
"""

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

# Add parent directory to path for imports when running as script
if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root))

from core.market_data.websocket_provider import BitfinexWebSocketCandleProvider
from core.types import Candle

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def format_candle(candle: Candle) -> str:
    """Format candle for display."""
    return (
        f"{candle.open_time.strftime('%Y-%m-%d %H:%M:%S')} | "
        f"{candle.symbol:10s} | "
        f"O: {float(candle.open):>10.2f} | "
        f"H: {float(candle.high):>10.2f} | "
        f"L: {float(candle.low):>10.2f} | "
        f"C: {float(candle.close):>10.2f} | "
        f"V: {float(candle.volume):>12.2f}"
    )


def main():
    parser = argparse.ArgumentParser(description="Stream real-time candle updates via WebSocket")
    parser.add_argument("--symbol", default="BTCUSD", help="Trading pair symbol (default: BTCUSD)")
    parser.add_argument(
        "--timeframe",
        default="1m",
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        help="Candle timeframe (default: 1m)",
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="How long to run in seconds (default: 60, 0 = forever)"
    )

    args = parser.parse_args()

    # Create provider
    provider = BitfinexWebSocketCandleProvider()

    # Track received candles
    candle_count = 0

    # Callback for candle updates
    def on_candle(candle: Candle) -> None:
        nonlocal candle_count
        candle_count += 1
        print(f"[{candle_count:3d}] {format_candle(candle)}")

    # Subscribe to symbol
    logger.info(f"Subscribing to {args.symbol} {args.timeframe} candles...")
    provider.subscribe(args.symbol, args.timeframe, on_candle)

    # Start WebSocket
    logger.info("Starting WebSocket connection...")
    provider.start()

    # Wait for connection
    time.sleep(2)

    if not provider.is_connected():
        logger.error("Failed to connect to WebSocket")
        return 1

    logger.info(f"Connected! Streaming {args.symbol} {args.timeframe} candles...")
    logger.info("Press Ctrl+C to stop\n")

    # Print header
    print(f"{'Time':^19} | {'Symbol':^10} | {'Open':^12} | {'High':^12} | {'Low':^12} | {'Close':^12} | {'Volume':^14}")
    print("-" * 120)

    # Handle Ctrl+C gracefully
    stop_event = False

    def signal_handler(sig, frame):
        nonlocal stop_event
        logger.info("\nStopping...")
        stop_event = True

    signal.signal(signal.SIGINT, signal_handler)

    # Run for specified duration or forever
    start_time = time.time()

    try:
        while not stop_event:
            if args.duration > 0 and (time.time() - start_time) > args.duration:
                break

            time.sleep(1)

    finally:
        # Stop provider
        logger.info("Stopping WebSocket provider...")
        provider.stop()

        print("\n" + "=" * 120)
        logger.info(f"Received {candle_count} candle updates")
        logger.info("Done!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
