from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

from core.arbitrage.calculator import ArbitrageComputation, calculate_arbitrage_profit
from core.types import FeeBreakdown


@dataclass(frozen=True)
class PriceSnapshot:
    exchange: str
    symbol: str
    price: Decimal


@dataclass(frozen=True)
class ArbitrageOpportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: Decimal
    sell_price: Decimal
    spread_pct: Decimal
    net_profit: Decimal
    net_profit_pct: Decimal
    total_fees: Decimal


class ArbitrageDetector:
    def __init__(
        self,
        *,
        fee_breakdowns: Mapping[str, FeeBreakdown],
        min_profit_pct: Decimal = Decimal("0.5"),
        withdrawal_fee: Decimal = Decimal("0"),
        network_fee: Decimal = Decimal("0"),
    ) -> None:
        self._fee_breakdowns = fee_breakdowns
        self._min_profit_pct = min_profit_pct
        self._withdrawal_fee = withdrawal_fee
        self._network_fee = network_fee

    def detect(self, prices: Iterable[PriceSnapshot]) -> list[ArbitrageOpportunity]:
        grouped: dict[str, list[PriceSnapshot]] = {}
        for snapshot in prices:
            grouped.setdefault(snapshot.symbol, []).append(snapshot)

        opportunities: list[ArbitrageOpportunity] = []

        for symbol, snapshots in grouped.items():
            if len(snapshots) < 2:
                continue
            buy = min(snapshots, key=lambda s: s.price)
            sell = max(snapshots, key=lambda s: s.price)
            if sell.price <= buy.price:
                continue

            buy_fees = self._fee_breakdowns.get(buy.exchange)
            sell_fees = self._fee_breakdowns.get(sell.exchange)
            if buy_fees is None or sell_fees is None:
                continue

            computation = calculate_arbitrage_profit(
                symbol=symbol,
                buy_exchange=buy.exchange,
                sell_exchange=sell.exchange,
                buy_price=buy.price,
                sell_price=sell.price,
                amount=Decimal("1"),
                buy_fees=buy_fees,
                sell_fees=sell_fees,
                withdrawal_fee=self._withdrawal_fee,
                network_fee=self._network_fee,
            )

            if computation.net_profit_pct < self._min_profit_pct:
                continue

            opportunities.append(_to_opportunity(computation))

        opportunities.sort(key=lambda opp: opp.net_profit_pct, reverse=True)
        return opportunities


def _to_opportunity(computation: ArbitrageComputation) -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        symbol=computation.symbol,
        buy_exchange=computation.buy_exchange,
        sell_exchange=computation.sell_exchange,
        buy_price=computation.buy_price,
        sell_price=computation.sell_price,
        spread_pct=computation.spread_pct,
        net_profit=computation.net_profit,
        net_profit_pct=computation.net_profit_pct,
        total_fees=computation.total_fees,
    )
