#!/usr/bin/env python3
"""Generate daily coin dossier entries for all tracked pairs.

Designed to be run via systemd timer (daily) or manually.

Usage:
    python -m scripts.generate_dossiers
    python -m scripts.generate_dossiers --exchange bitfinex
    python -m scripts.generate_dossiers --symbol BTCUSD
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
        logger.info(f"🔄 Generating dossiers for all pairs on {args.exchange}")
        entries = await svc.generate_all(args.exchange)
        elapsed = time.monotonic() - start

        for entry in entries:
            status = "✅" if entry.id else "❌"
            logger.info(f"  {status} {entry.symbol}: {entry.predicted_direction} → ${entry.predicted_target:,.2f}")

        logger.info(f"\n📊 Summary: {len(entries)} dossiers generated in {elapsed:.1f}s")

    total_elapsed = time.monotonic() - start
    logger.info(f"⏱️  Total time: {total_elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
