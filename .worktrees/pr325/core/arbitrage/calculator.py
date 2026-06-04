from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.fees.model import FeeModel
from core.types import FeeBreakdown

PERCENT = Decimal("100")


@dataclass(frozen=True)
class ArbitrageComputation:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: Decimal
    sell_price: Decimal
    spread_pct: Decimal
    gross_profit: Decimal
    total_fees: Decimal
    net_profit: Decimal
    net_profit_pct: Decimal


def calculate_arbitrage_profit(
    *,
    symbol: str,
    buy_exchange: str,
    sell_exchange: str,
    buy_price: Decimal,
    sell_price: Decimal,
    amount: Decimal,
    buy_fees: FeeBreakdown,
    sell_fees: FeeBreakdown,
    withdrawal_fee: Decimal = Decimal("0"),
    network_fee: Decimal = Decimal("0"),
) -> ArbitrageComputation:
    if amount <= 0:
        raise ValueError("amount must be positive")

    buy_notional = buy_price * amount
    sell_notional = sell_price * amount
    if buy_notional <= 0:
        raise ValueError("buy_price must be positive")

    spread_pct = ((sell_price - buy_price) / buy_price) * PERCENT
    gross_profit = (sell_price - buy_price) * amount

    buy_cost = FeeModel(buy_fees).estimate_cost(gross_notional=buy_notional, taker=True)
    sell_cost = FeeModel(sell_fees).estimate_cost(gross_notional=sell_notional, taker=True)
    total_fees = buy_cost.estimated_total_cost + sell_cost.estimated_total_cost + withdrawal_fee + network_fee
    net_profit = gross_profit - total_fees
    net_profit_pct = (net_profit / buy_notional) * PERCENT

    return ArbitrageComputation(
        symbol=symbol,
        buy_exchange=buy_exchange,
        sell_exchange=sell_exchange,
        buy_price=buy_price,
        sell_price=sell_price,
        spread_pct=spread_pct,
        gross_profit=gross_profit,
        total_fees=total_fees,
        net_profit=net_profit,
        net_profit_pct=net_profit_pct,
    )
