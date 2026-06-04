from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.arbitrage.detector import ArbitrageDetector, PriceSnapshot
from core.types import FeeBreakdown


def _default_fees() -> FeeBreakdown:
    return FeeBreakdown(
        currency="USD",
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.002"),
        assumed_spread_bps=10,
        assumed_slippage_bps=5,
    )


def test_detector_finds_profitable_opportunity() -> None:
    detector = ArbitrageDetector(
        fee_breakdowns={"bitfinex": _default_fees(), "binance": _default_fees()},
        min_profit_pct=Decimal("0.5"),
    )

    snapshots = [
        PriceSnapshot(exchange="bitfinex", symbol="BTCUSD", price=Decimal("100")),
        PriceSnapshot(exchange="binance", symbol="BTCUSD", price=Decimal("105")),
    ]

    opportunities = detector.detect(snapshots)

    assert len(opportunities) == 1
    opp = opportunities[0]
    assert opp.buy_exchange == "bitfinex"
    assert opp.sell_exchange == "binance"
    assert opp.symbol == "BTCUSD"
    assert opp.net_profit_pct >= Decimal("0.5")


def test_detector_filters_below_threshold() -> None:
    detector = ArbitrageDetector(
        fee_breakdowns={"bitfinex": _default_fees(), "binance": _default_fees()},
        min_profit_pct=Decimal("10"),
    )

    snapshots = [
        PriceSnapshot(exchange="bitfinex", symbol="BTCUSD", price=Decimal("100")),
        PriceSnapshot(exchange="binance", symbol="BTCUSD", price=Decimal("101")),
    ]

    opportunities = detector.detect(snapshots)

    assert opportunities == []
