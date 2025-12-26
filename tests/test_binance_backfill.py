from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data import binance_backfill as backfill


def test_parse_dt_date_returns_utc_midnight() -> None:
    dt = backfill._parse_dt("2024-03-01")
    assert dt == datetime(2024, 3, 1, tzinfo=timezone.utc)


def test_parse_dt_converts_offset_to_utc() -> None:
    dt = backfill._parse_dt("2024-03-01T02:30:00+02:00")
    assert dt == datetime(2024, 3, 1, 0, 30, tzinfo=timezone.utc)
    assert dt.tzinfo == timezone.utc


def test_normalize_binance_symbol_converts_btcusd_to_btcusdt() -> None:
    assert backfill._normalize_binance_symbol("BTCUSD") == "BTCUSDT"


def test_normalize_binance_symbol_removes_separators() -> None:
    assert backfill._normalize_binance_symbol("BTC/USDT") == "BTCUSDT"
    assert backfill._normalize_binance_symbol("BTC:USDT") == "BTCUSDT"


def test_normalize_binance_symbol_uppercases() -> None:
    assert backfill._normalize_binance_symbol("btcusdt") == "BTCUSDT"


def test_normalize_binance_symbol_trims_whitespace() -> None:
    assert backfill._normalize_binance_symbol(" BTCUSDT ") == "BTCUSDT"


def test_normalize_binance_symbol_requires_value() -> None:
    with pytest.raises(ValueError):
        backfill._normalize_binance_symbol("   ")


def test_build_arg_parser_includes_backoff_parameters() -> None:
    """Verify that backoff/jitter CLI arguments are present and have correct defaults."""
    parser = backfill.build_arg_parser()
    args = parser.parse_args(["--symbol", "BTCUSDT", "--timeframe", "1h", "--start", "2024-01-01"])

    assert args.max_retries == 6
    assert args.initial_backoff_seconds == 0.5
    assert args.max_backoff_seconds == 8.0
    assert args.jitter_seconds == 0.0


def test_build_arg_parser_accepts_custom_backoff_values() -> None:
    """Verify that custom backoff values can be parsed."""
    parser = backfill.build_arg_parser()
    args = parser.parse_args(
        [
            "--symbol", "BTCUSDT",
            "--timeframe", "1h",
            "--start", "2024-01-01",
            "--max-retries", "10",
            "--initial-backoff-seconds", "1.0",
            "--max-backoff-seconds", "16.0",
            "--jitter-seconds", "0.5",
        ]
    )

    assert args.max_retries == 10
    assert args.initial_backoff_seconds == 1.0
    assert args.max_backoff_seconds == 16.0
    assert args.jitter_seconds == 0.5


def test_build_arg_parser_defaults_exchange_to_binance() -> None:
    """Verify that --exchange defaults to binance."""
    parser = backfill.build_arg_parser()
    args = parser.parse_args(["--symbol", "BTCUSDT", "--timeframe", "1h", "--start", "2024-01-01"])
    assert args.exchange == "binance"
