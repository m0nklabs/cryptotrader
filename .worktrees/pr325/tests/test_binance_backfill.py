from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data import binance_backfill as backfill


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("BTCUSD", "BTCUSDT"),
        ("ethusd", "ETHUSDT"),
        ("SOL/USD", "SOLUSDT"),
        ("XRPUSDT", "XRPUSDT"),
    ],
)
def test_normalize_binance_symbol_converts_known_usd_pairs(symbol: str, expected: str) -> None:
    assert backfill._normalize_binance_symbol(symbol) == expected


def test_normalize_binance_symbol_keeps_unknown_usd_pair() -> None:
    assert backfill._normalize_binance_symbol("FOOUSD") == "FOOUSD"


def test_normalize_binance_symbol_requires_value() -> None:
    with pytest.raises(ValueError):
        backfill._normalize_binance_symbol("   ")


def test_build_arg_parser_includes_backoff_parameters() -> None:
    parser = backfill.build_arg_parser()
    args = parser.parse_args(["--symbol", "BTCUSD", "--timeframe", "1h", "--start", "2024-01-01"])

    assert args.max_retries == 6
    assert args.initial_backoff_seconds == 0.5
    assert args.max_backoff_seconds == 8.0
    assert args.jitter_seconds == 0.0


def test_fetch_binance_klines_page_uses_backoff_params() -> None:
    with (
        patch("core.market_data.binance_backfill.requests.get") as mock_get,
        patch("core.market_data.binance_backfill.time.sleep") as mock_sleep,
    ):
        mock_resp_429 = Mock()
        mock_resp_429.status_code = 429

        mock_resp_ok = Mock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = []

        mock_get.side_effect = [mock_resp_429, mock_resp_ok]

        result = backfill._fetch_binance_klines_page(
            symbol="BTCUSDT",
            timeframe_api="1h",
            start_ms=1000000,
            end_ms=2000000,
            initial_backoff_seconds=2.0,
            max_backoff_seconds=10.0,
            jitter_seconds=0.0,
            max_retries=3,
        )

        assert result == []
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(2.0)
