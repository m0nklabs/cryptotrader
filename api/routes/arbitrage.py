"""API endpoints for arbitrage detection."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.arbitrage.detector import ArbitrageDetector, PriceSnapshot
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores
from core.types import FeeBreakdown

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])

_stores: PostgresStores | None = None


def _get_stores() -> PostgresStores:
    global _stores
    if _stores is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise HTTPException(status_code=500, detail="DATABASE_URL is not set")
        _stores = PostgresStores(config=PostgresConfig(database_url=database_url))
    return _stores


DEFAULT_FEE = FeeBreakdown(
    currency="USD",
    maker_fee_rate=Decimal("0.001"),
    taker_fee_rate=Decimal("0.002"),
    assumed_spread_bps=10,
    assumed_slippage_bps=5,
)


def _parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@router.get("/opportunities")
async def get_arbitrage_opportunities(
    exchanges: str = Query("bitfinex,binance", description="Comma-separated exchanges"),
    timeframe: str = Query("1m", description="Timeframe to compare"),
    symbols: str | None = Query(None, description="Optional comma-separated symbols"),
    min_profit_pct: float = Query(0.5, ge=0, description="Minimum net profit percent after fees"),
    withdrawal_fee: float = Query(0.0, ge=0, description="Withdrawal fee in quote currency"),
    network_fee: float = Query(0.0, ge=0, description="Network fee in quote currency"),
) -> dict[str, Any]:
    exchange_list = _parse_list(exchanges)
    if not exchange_list:
        raise HTTPException(status_code=400, detail="At least one exchange is required")

    symbol_list = _parse_list(symbols)

    stores = _get_stores()
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    price_snapshots: list[PriceSnapshot] = []
    with engine.begin() as conn:
        if not symbol_list:
            for exchange in exchange_list:
                rows = conn.execute(
                    text(
                        """
                        SELECT DISTINCT symbol
                        FROM candles
                        WHERE exchange = :exchange AND timeframe = :timeframe
                        ORDER BY symbol
                        """
                    ),
                    {"exchange": exchange, "timeframe": timeframe},
                ).fetchall()
                symbol_list.extend([row[0] for row in rows])

            symbol_list = sorted(set(symbol_list))

        for exchange in exchange_list:
            for symbol in symbol_list:
                row = conn.execute(
                    text(
                        """
                        SELECT close
                        FROM candles
                        WHERE exchange = :exchange AND symbol = :symbol AND timeframe = :timeframe
                        ORDER BY open_time DESC
                        LIMIT 1
                        """
                    ),
                    {"exchange": exchange, "symbol": symbol, "timeframe": timeframe},
                ).fetchone()
                if not row:
                    continue
                price = Decimal(str(row[0]))
                price_snapshots.append(PriceSnapshot(exchange=exchange, symbol=symbol, price=price))

    fee_map = {exchange: DEFAULT_FEE for exchange in exchange_list}
    detector = ArbitrageDetector(
        fee_breakdowns=fee_map,
        min_profit_pct=Decimal(str(min_profit_pct)),
        withdrawal_fee=Decimal(str(withdrawal_fee)),
        network_fee=Decimal(str(network_fee)),
    )

    opportunities = detector.detect(price_snapshots)

    return {
        "exchanges": exchange_list,
        "timeframe": timeframe,
        "opportunities": [
            {
                "symbol": opp.symbol,
                "buy_exchange": opp.buy_exchange,
                "sell_exchange": opp.sell_exchange,
                "buy_price": float(opp.buy_price),
                "sell_price": float(opp.sell_price),
                "spread_pct": float(opp.spread_pct),
                "net_profit": float(opp.net_profit),
                "net_profit_pct": float(opp.net_profit_pct),
                "total_fees": float(opp.total_fees),
            }
            for opp in opportunities
        ],
        "count": len(opportunities),
    }
