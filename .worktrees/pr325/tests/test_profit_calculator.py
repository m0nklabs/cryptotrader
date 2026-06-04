from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.arbitrage.calculator import calculate_arbitrage_profit
from core.types import FeeBreakdown


def test_calculate_arbitrage_profit_accounts_for_fees() -> None:
    fees = FeeBreakdown(
        currency="USD",
        maker_fee_rate=Decimal("0.001"),
        taker_fee_rate=Decimal("0.002"),
        assumed_spread_bps=10,
        assumed_slippage_bps=5,
    )

    result = calculate_arbitrage_profit(
        symbol="BTCUSD",
        buy_exchange="bitfinex",
        sell_exchange="binance",
        buy_price=Decimal("100"),
        sell_price=Decimal("105"),
        amount=Decimal("1"),
        buy_fees=fees,
        sell_fees=fees,
        withdrawal_fee=Decimal("0"),
        network_fee=Decimal("0"),
    )

    assert result.spread_pct == Decimal("5")
    assert result.total_fees == Decimal("0.71750000")
    assert result.net_profit == Decimal("4.28250000")
    assert result.net_profit_pct == Decimal("4.28250000")
