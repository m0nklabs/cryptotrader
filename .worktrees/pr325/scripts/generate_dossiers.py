#!/usr/bin/env python3
"""Generate daily coin dossier entries for all tracked pairs.

Designed to be run via systemd timer (daily) or manually.
Supports staggered generation to spread hardware load.

Usage:
    python -m scripts.generate_dossiers
    python -m scripts.generate_dossiers --exchange bitfinex
    python -m scripts.generate_dossiers --symbol BTCUSD
    python -m scripts.generate_dossiers --delay 15  # 15s between each coin
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dossier.service import DossierService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dossier-generator")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily coin dossier entries")
    parser.add_argument(
        "--exchange",
        default="bitfinex",
        help="Exchange to generate dossiers for (default: bitfinex)",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Generate for a single symbol only (e.g. BTCUSD)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the Ollama model to use",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=10.0,
        help="Seconds to wait between each coin generation (default: 10)",
    )
    args = parser.parse_args()

    svc = DossierService(model=args.model)

    start = time.monotonic()

    if args.symbol:
        logger.info(f"📝 Generating dossier for {args.exchange}:{args.symbol}")
        try:
            entry = await svc.generate_entry(args.exchange, args.symbol.upper())
            logger.info(
                f"✅ {entry.symbol}: {entry.predicted_direction} → "
                f"${entry.predicted_target:,.2f} "
                f"({entry.tokens_used} tokens, {entry.generation_time_ms}ms)"
            )
        except Exception as e:
            logger.error(f"❌ Failed: {e}")
            sys.exit(1)
    else:
        logger.info(f"🔄 Generating dossiers for all pairs on {args.exchange} (delay: {args.delay}s)")
        symbols = await svc._get_available_symbols(args.exchange)
        logger.info(f"📋 Found {len(symbols)} symbols")

        entries = []
        for i, symbol in enumerate(symbols):
            try:
                logger.info(f"📝 [{i + 1}/{len(symbols)}] {symbol}...")
                entry = await svc.generate_entry(args.exchange, symbol)
                entries.append(entry)
                logger.info(
                    f"  ✅ {entry.symbol}: {entry.predicted_direction} → "
                    f"${entry.predicted_target:,.2f} "
                    f"({entry.tokens_used} tokens, {entry.generation_time_ms}ms)"
                )
            except Exception as e:
                logger.error(f"  ❌ {symbol}: {e}")

            # Stagger: wait between coins to spread hw load
            if i < len(symbols) - 1 and args.delay > 0:
                logger.debug(f"  ⏳ Waiting {args.delay}s...")
                await asyncio.sleep(args.delay)

        elapsed = time.monotonic() - start
        logger.info(f"\n📊 Summary: {len(entries)}/{len(symbols)} dossiers generated in {elapsed:.1f}s")

    total_elapsed = time.monotonic() - start
    logger.info(f"⏱️  Total time: {total_elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
