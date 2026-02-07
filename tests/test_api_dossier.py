from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pytest

from api.routes.dossier import _entry_to_dict


@dataclass
class _StubEntry:
    id: int = 1
    exchange: str = "bitfinex"
    symbol: str = "BTCUSD"
    entry_date: date = date(2026, 2, 7)

    price: object = Decimal("50000.12")
    change_24h: object = Decimal("1.23")
    change_7d: object = "-2.50"
    volume_24h: object = Decimal("12345.67")
    rsi: object = Decimal("55.5")
    macd_signal: str = "bullish"
    ema_trend: str = "up"
    support_level: object = None
    resistance_level: object = Decimal("51000")
    signal_score: object = Decimal("42")

    lore: str = ""
    stats_summary: str = ""
    tech_analysis: str = ""
    retrospective: str = ""
    prediction: str = ""
    full_narrative: str = ""

    predicted_direction: str = "UP"
    predicted_target: object = Decimal("50500")
    predicted_timeframe: str = "24h"
    prediction_correct: bool | None = None

    model_used: str = "llama3"
    tokens_used: int = 123
    generation_time_ms: int = 456
    created_at: datetime | None = None


@pytest.mark.parametrize(
    "field",
    [
        "price",
        "change_24h",
        "change_7d",
        "volume_24h",
        "rsi",
        "support_level",
        "resistance_level",
        "signal_score",
        "predicted_target",
    ],
)
def test_entry_to_dict_coerces_numeric_fields_to_float(field: str) -> None:
    payload = _entry_to_dict(_StubEntry())
    assert field in payload
    assert isinstance(payload[field], float)
