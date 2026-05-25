#!/usr/bin/env python3
"""Research the top Bitfinex USD pairs by volume."""

from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient


def _top_usd_symbols(client: BitfinexClient, limit: int = 20) -> list[str]:
    trading_pairs = client.get_trading_pairs()
    usd_pairs = [pair for pair in trading_pairs if pair.endswith("USD") and ":" not in pair]
    symbols = [f"t{pair}" for pair in usd_pairs]
    tickers = client.get_tickers(symbols)
    ranked = sorted(tickers, key=lambda item: item.get("volume", 0.0), reverse=True)
    return [item["symbol"] for item in ranked[:limit]]


def _average_range_percent(candles: list[dict]) -> float:
    if not candles:
        return 0.0

    total = 0.0
    counted = 0
    for candle in candles:
        low = candle.get("low", 0.0)
        high = candle.get("high", 0.0)
        close = candle.get("close", 0.0)
        if low > 0 and high >= low and close > 0:
            total += ((high - low) / close) * 100
            counted += 1
    return total / counted if counted else 0.0


def research_top20():
    client = BitfinexClient()

    print("=" * 60)
    print("STEP 1: Get Top 20 Coins")
    print("=" * 60)

    try:
        symbols = _top_usd_symbols(client, limit=20)
        print(f"✓ Successfully ranked {len(symbols)} USD pairs by volume")
        for symbol in symbols:
            print(f"  {symbol}")
    except Exception as exc:
        print(f"✗ {exc}")
        return

    print("\n" + "=" * 60)
    print("STEP 2: Analyze Each Coin")
    print("=" * 60)

    results = []
    for coin_sym in symbols:
        print(f"\nAnalyzing {coin_sym}...")

        try:
            ticker = client.get_ticker(coin_sym)
            orderbook = client.get_orderbook(coin_sym, length=25)
            candles = client.get_candles("1h", coin_sym, limit=24)

            if ticker.get("error"):
                raise RuntimeError(ticker["error"])

            best_bid = orderbook["bids"][0]["price"] if orderbook["bids"] else 0.0
            best_ask = orderbook["asks"][0]["price"] if orderbook["asks"] else 0.0
            spread_abs = max(best_ask - best_bid, 0.0)
            spread_pct = (spread_abs / best_ask) * 100 if best_ask else 0.0
            day_change_pct = ticker.get("daily_change_relative", 0.0) * 100
            avg_range_pct = _average_range_percent(candles)

            result = {
                "symbol": coin_sym,
                "price": ticker.get("last_price", 0.0),
                "spread_pct": spread_pct,
                "day_change_pct": day_change_pct,
                "avg_range_pct": avg_range_pct,
                "volume": ticker.get("volume", 0.0),
            }
            results.append(result)

            print(
                f"  ✓ spread {spread_pct:.4f}% | "
                f"24h change {day_change_pct:.2f}% | "
                f"avg 1h range {avg_range_pct:.2f}%"
            )
        except Exception as exc:
            print(f"  ✗ {str(exc)[:80]}")

    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)

    if not results:
        print("\nNo actionable opportunities found among top 20.")
        return

    ranked = sorted(results, key=lambda item: (item["spread_pct"], item["avg_range_pct"]), reverse=True)
    print(f"\nTop {min(10, len(ranked))} markets by spread + movement:\n")
    for result in ranked[:10]:
        print(
            f"{result['symbol']}: price {result['price']:.4f} | "
            f"spread {result['spread_pct']:.4f}% | "
            f"24h change {result['day_change_pct']:.2f}% | "
            f"avg 1h range {result['avg_range_pct']:.2f}% | "
            f"volume {result['volume']:.2f}"
        )


if __name__ == "__main__":
    research_top20()
