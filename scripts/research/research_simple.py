#!/usr/bin/env python3
"""Simple research using direct HTTP requests."""

import sys

sys.path.insert(0, ".")


def research():
    print("Researching top 20 coins on Bitfinex...")

    base_url = "https://api.binance.com"
    coins_to_check = [
        "BTCUSDT",
        "ETHUSDT",
        "XRPUSDT",
        "BCHUSDT",
        "LTCUSDT",
        "ADAUSDT",
        "DOGEUSDT",
        "DOTUSDT",
        "MATICUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "UNIUSDT",
        "SNMUSDT",
        "NEARUSDT",
        "ALGOUSDT",
        "APEUSDT",
        "FILUSDT",
        "SOLUSD",
        "MKRUSDT",
        "ZECUSDT",
    ]

    results = {}

    for symbol in coins_to_check:
        try:
            import requests

            ticker = f"{base_url}/api/v3/ticker/spot?symbol={symbol}"
            resp = requests.get(ticker, timeout=5)
            if resp.status_code != 200:
                continue

            data = resp.json()
            current_price = data.get("lastPrice") or data.get("price", "N/A")

            orderbook_url = f"{base_url}/api/v3/orderbook?symbol={symbol}&limit=5"
            orderbook_resp = requests.get(orderbook_url, timeout=5)
            if orderbook_resp.status_code != 200:
                continue

            orderbook_data = orderbook_resp.json()
            bids = orderbook_data.get("bids", [])
            asks = orderbook_data.get("asks", [])
            best_bid = bids[0][0] if bids else None
            best_ask = asks[0][0] if asks else None
            spread = float(best_ask) - float(best_bid) if best_bid and best_ask else 0

            results[symbol] = {
                "price": current_price,
                "bid/ask": f"{best_bid}/{best_ask}" if best_bid and best_ask else "N/A",
                "spread": spread,
            }

        except Exception as exc:
            results[symbol] = {"error": str(exc)}

    print(f"\n{'=' * 60}")
    print(f"RESEARCHED {len(results)} COINS")
    print(f"{'=' * 60}\n")

    actionable = [
        (symbol, data) for symbol, data in results.items() if "error" not in data and data.get("spread", 0) > 0.001
    ]

    if not actionable:
        print("No actionable opportunities found.")
        return

    print(f"{len(actionable)} coins with actionable spreads:\n")
    for symbol, data in actionable[:10]:
        spread = data.get("spread", 0)
        bid_ask = data.get("bid/ask", "N/A")
        if spread > 0.05:
            print(f"{symbol}: spread {spread:.3f} | {bid_ask}")
        else:
            print(f"{symbol}: spread {spread:.4f} | {bid_ask}")


if __name__ == "__main__":
    research()
