#!/usr/bin/env python3
"""Quick debug script for D1 candles."""

import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://cryptotrader:cryptotrader@localhost:5432/cryptotrader")
    try:
        # Check candle counts per timeframe
        rows = await conn.fetch(
            """
            SELECT timeframe, COUNT(*) as cnt
            FROM candles
            GROUP BY timeframe
            ORDER BY cnt DESC
        """
        )
        print("=== Candle counts by timeframe ===")
        for r in rows:
            print(f"  {r['timeframe']}: {r['cnt']:,}")

        # Check 1d specifically
        rows = await conn.fetch(
            """
            SELECT symbol, COUNT(*) as cnt
            FROM candles
            WHERE timeframe = '1d'
            GROUP BY symbol
            ORDER BY cnt DESC
        """
        )
        print("\n=== 1d candles by symbol ===")
        for r in rows:
            print(f"  {r['symbol']}: {r['cnt']}")

        # Check recent 1d candle dates
        rows = await conn.fetch(
            """
            SELECT symbol, MIN(open_time) as oldest, MAX(open_time) as newest
            FROM candles
            WHERE timeframe = '1d'
            GROUP BY symbol
            LIMIT 5
        """
        )
        print("\n=== 1d date ranges ===")
        for r in rows:
            print(f"  {r['symbol']}: {r['oldest']} to {r['newest']}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
