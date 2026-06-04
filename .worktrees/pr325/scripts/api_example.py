#!/usr/bin/env python3
"""Example usage of the FastAPI read-only API.

This script demonstrates how to:
1. Check API health
2. Query latest candles

Requirements:
    - API server running (python scripts/run_api.py)
    - DATABASE_URL set with populated candles table
"""

import requests


def main():
    """Run API examples."""
    base_url = "http://127.0.0.1:8000"

    print("=" * 60)
    print("FastAPI Read-Only API - Example Usage")
    print("=" * 60)
    print()

    # Example 1: Health check
    print("1. Health Check")
    print("-" * 60)
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")
    print()

    # Example 2: Get latest candles
    print("2. Get Latest Candles (BTCUSD, 1h)")
    print("-" * 60)
    try:
        params = {
            "exchange": "bitfinex",
            "symbol": "BTCUSD",
            "timeframe": "1h",
            "limit": 5,
        }
        response = requests.get(f"{base_url}/candles/latest", params=params, timeout=5)
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Exchange: {data.get('exchange')}")
        print(f"Symbol: {data.get('symbol')}")
        print(f"Timeframe: {data.get('timeframe')}")
        print(f"Count: {data.get('count')}")
        print(f"Latest Open Time: {data.get('latest_open_time')}")
        print()
        print("Sample Candles:")
        for candle in data.get("candles", [])[:3]:
            print(f"  - Time: {candle['open_time']}, Close: {candle['close']}")
    except Exception as e:
        print(f"Error: {e}")
    print()

    print("=" * 60)
    print("For API documentation, visit:")
    print(f"  - Swagger UI: {base_url}/docs")
    print(f"  - ReDoc: {base_url}/redoc")
    print("=" * 60)


if __name__ == "__main__":
    main()
