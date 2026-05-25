#!/usr/bin/env python3
"""Minimal Bitfinex market snapshot for 20 common USD pairs."""

from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient


def research():
    print("Researching Bitfinex top 20 coins...")

    try:
        client = BitfinexClient()
        symbols = [
            "tBTCUSD",
            "tETHUSD",
            "tXRPUSD",
            "tLTCUSD",
            "tEOSUSD",
            "tBCHUSD",
            "tADAUSD",
            "tXMRUSD",
            "tDOTUSD",
            "tZECUSD",
            "tALGOUSD",
            "tAVAXUSD",
            "tLINKUSD",
            "tMATICUSD",
            "tUNIUSD",
            "tFILUSD",
            "tNEARUSD",
            "tDOGEUSD",
            "tSOLUSD",
            "tAPEUSD",
        ]
        print(f"Fetching {len(symbols)} tickers via REST...")
        tickers = client.get_tickers(symbols)
        ticker_data = {entry["symbol"]: entry for entry in tickers}

        print("\n" + "=" * 60)
        print("TICKER DATA RECEIVED")
        print("=" * 60)

        for sym in symbols[:5]:
            data = ticker_data.get(sym)
            if data:
                last = data.get("last_price", "N/A")
                change = data.get("daily_change_relative", 0.0)
                print(f"{sym}: {last} ({change:.4%})")
            else:
                print(f"{sym}: ✗ no data")

    except Exception as exc:
        print(f"✗ {exc}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    research()
