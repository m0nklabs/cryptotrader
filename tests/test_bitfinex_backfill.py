from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data import bitfinex_backfill as backfill


def test_parse_dt_date_returns_utc_midnight() -> None:
    dt = backfill._parse_dt("2024-03-01")
    assert dt == datetime(2024, 3, 1, tzinfo=timezone.utc)


def test_parse_dt_converts_offset_to_utc() -> None:
    dt = backfill._parse_dt("2024-03-01T02:30:00+02:00")
    assert dt == datetime(2024, 3, 1, 0, 30, tzinfo=timezone.utc)
    assert dt.tzinfo == timezone.utc


def test_normalize_bitfinex_symbol_adds_prefix_and_trims() -> None:
    assert backfill._normalize_bitfinex_symbol(" BTCUSD ") == "tBTCUSD"


def test_normalize_bitfinex_symbol_requires_value() -> None:
    with pytest.raises(ValueError):
        backfill._normalize_bitfinex_symbol("   ")
