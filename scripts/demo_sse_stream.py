#!/usr/bin/env python3
"""Demo script showing WebSocket candle streaming via SSE.

This demonstrates the end-to-end flow:
1. Backend connects to Bitfinex WebSocket
2. Backend receives candle updates
3. Backend broadcasts to SSE clients
4. Client receives real-time updates

Note: This is for demonstration only. In production, the FastAPI server
handles SSE streaming automatically.

Usage:
    python scripts/demo_sse_stream.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Ensure imports work when invoked as a script
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def demo_websocket_provider():
    """Demonstrate WebSocket provider connecting to Bitfinex."""
    from core.market_data.websocket_provider import BitfinexWebSocketCandleProvider

    print("=" * 60)
    print("WebSocket Candle Provider Demo")
    print("=" * 60)
    print("\nConnecting to Bitfinex WebSocket...")
    print("Symbol: BTCUSD, Timeframe: 1m")
    print("This will stream live candle updates from Bitfinex.\n")

    provider = BitfinexWebSocketCandleProvider()
    candles_received = []

    def on_candle(candle):
        """Callback for candle updates."""
        candles_received.append(candle)
        print(f"✓ Candle received: {candle.symbol} @ {candle.close} (volume: {candle.volume})")
        print(f"  Open Time: {candle.open_time}")
        print(f"  OHLC: {candle.open} / {candle.high} / {candle.low} / {candle.close}")

    # Subscribe to BTCUSD 1m candles
    provider.subscribe("BTCUSD", "1m", on_candle)
    provider.start()

    print("WebSocket connected! Waiting for candle updates...")
    print("(This may take up to 1 minute for the first update)\n")

    try:
        # Wait for up to 90 seconds to receive candles
        timeout = 90
        start_time = time.time()

        while len(candles_received) < 3 and (time.time() - start_time) < timeout:
            time.sleep(1)

            # Show connection status
            if int(time.time() - start_time) % 10 == 0:
                print(f"... waiting ({int(time.time() - start_time)}s elapsed, {len(candles_received)} candles received)")

        if candles_received:
            print(f"\n✓ Successfully received {len(candles_received)} candle(s)")
            print("\nThis demonstrates that:")
            print("1. WebSocket connection to Bitfinex works")
            print("2. Candle updates are received in real-time")
            print("3. Data is properly parsed and formatted")
        else:
            print("\n⚠ No candles received within timeout")
            print("This is normal if:")
            print("- Market is closed or low volume")
            print("- Network connectivity issues")
            print("- Bitfinex API is unavailable")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        print("\nStopping WebSocket provider...")
        provider.stop()
        print("✓ Disconnected")

    print("\n" + "=" * 60)
    print("Demo completed")
    print("=" * 60)


def demo_sse_integration():
    """Demonstrate SSE integration concept."""
    print("\n" + "=" * 60)
    print("SSE Integration Architecture")
    print("=" * 60)
    print("""
How real-time streaming works:

1. Frontend client:
   const es = new EventSource('/candles/stream?symbol=BTCUSD&timeframe=1m');
   es.onmessage = (event) => {
       const candle = JSON.parse(event.data);
       updateChart(candle);
   };

2. Backend FastAPI endpoint (/candles/stream):
   - Maintains WebSocket connection to Bitfinex
   - Broadcasts candle updates to all connected SSE clients
   - Handles reconnection automatically

3. Benefits:
   - Near-instant updates (< 1 second latency)
   - Automatic reconnection on disconnect
   - Graceful fallback to polling if needed
   - No increase in API rate limit usage

4. Fallback behavior:
   - If SSE fails, frontend automatically falls back to polling
   - Chart stays updated even if WebSocket is unavailable
   - Visual indicator shows connection status (⚡ when live)
    """)


def main() -> int:
    """Run demo."""
    import argparse

    parser = argparse.ArgumentParser(description="Demo WebSocket candle streaming")
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Skip live WebSocket connection (show architecture only)",
    )
    args = parser.parse_args()

    if not args.skip_live:
        print("\nThis demo will connect to live Bitfinex WebSocket API.")
        print("Press Ctrl+C to interrupt at any time.\n")
        time.sleep(1)

        demo_websocket_provider()

    demo_sse_integration()

    return 0


if __name__ == "__main__":
    sys.exit(main())
