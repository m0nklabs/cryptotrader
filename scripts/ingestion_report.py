#!/usr/bin/env python3

import argparse
import os
from typing import List, Tuple

from sqlalchemy import create_engine, text



DB_URL = os.environ.get("DATABASE_URL")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print ingestion summary for exchange/symbol/timeframe tuples."
    )
    parser.add_argument(
        "--exchange", 
        action="append",
        help="Exchange name (repeatable)"
    )
    parser.add_argument(
        "--symbol", 
        action="append",
        help="Symbol name (repeatable)"
    )
    parser.add_argument(
        "--timeframe", 
        action="append",
        help="Timeframe (repeatable)"
    )
    return parser.parse_args()


def validate_db_connection() -> bool:
    if not DB_URL:
        print("DATABASE_URL not set")
        return False
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        return True
    except Exception as e:
        print(f"DB connection failed: {e}")
        return False


def validate_schema() -> bool:
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'candles')"))
            if not result.fetchone()[0]:
                print("Schema missing: candles table not found")
                return False
        return True
    except Exception as e:
        print(f"Schema validation failed: {e}")
        return False


def get_ingestion_summary(
    exchange: ExchangeName,
    symbol: Symbol,
    timeframe: Timeframe
) -> dict:
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            query = text(
                """
                SELECT 
                    EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'candles') AS schema_ok,
                    COUNT(*) AS candles_count,
                    MAX(open_time) AS latest_candle_open_time
                FROM candles
                WHERE exchange = :exchange
                AND symbol = :symbol
                AND timeframe = :timeframe
                """
            )
            result = conn.execute(query, {
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": timeframe
            })
            row = result.fetchone()
            return {
                "schema_ok": row[0],
                "candles_count": row[1],
                "latest_candle_open_time": row[2]
            }
    except Exception as e:
        print(f"Error fetching data: {e}")
        return {}


def main() -> int:
    args = parse_args()
    exchanges = args.exchange or []
    symbols = args.symbol or []
    timeframes = args.timeframe or []

    if not exchanges or not symbols or not timeframes:
        print("Error: Must provide --exchange, --symbol, and --timeframe")
        return 1

    # Build list of tuples
    tuples = []
    for exchange in exchanges:
        for symbol in symbols:
            for timeframe in timeframes:
                tuples.append((exchange, symbol, timeframe))

    if not validate_db_connection():
        return 1

    if not validate_schema():
        return 1

    for exchange, symbol, timeframe in tuples:
        summary = get_ingestion_summary(exchange, symbol, timeframe)
        if not summary:
            return 1
        print(f"{exchange}/{symbol}/{timeframe} schema_ok={summary['schema_ok']} candles_count={summary['candles_count']} latest_candle_open_time={summary['latest_candle_open_time']}")

    return 0


if __name__ == "__main__":
    exit(main())
