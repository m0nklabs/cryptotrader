from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest.mock import Mock, patch

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


def test_build_arg_parser_includes_backoff_parameters() -> None:
    """Verify that backoff/jitter CLI arguments are present and have correct defaults."""
    parser = backfill.build_arg_parser()
    args = parser.parse_args(["--symbol", "BTCUSD", "--timeframe", "1h", "--start", "2024-01-01"])

    assert args.max_retries == 6
    assert args.initial_backoff_seconds == 0.5
    assert args.max_backoff_seconds == 8.0
    assert args.jitter_seconds == 0.0


def test_build_arg_parser_accepts_custom_backoff_values() -> None:
    """Verify that custom backoff values can be parsed."""
    parser = backfill.build_arg_parser()
    args = parser.parse_args(
        [
            "--symbol",
            "BTCUSD",
            "--timeframe",
            "1h",
            "--start",
            "2024-01-01",
            "--max-retries",
            "10",
            "--initial-backoff-seconds",
            "1.0",
            "--max-backoff-seconds",
            "16.0",
            "--jitter-seconds",
            "2.5",
        ]
    )

    assert args.max_retries == 10
    assert args.initial_backoff_seconds == 1.0
    assert args.max_backoff_seconds == 16.0
    assert args.jitter_seconds == 2.5


def test_fetch_bitfinex_candles_page_uses_backoff_params() -> None:
    """Verify that backoff parameters affect the retry logic."""
    with patch("core.market_data.bitfinex_backfill.requests.get") as mock_get, patch(
        "core.market_data.bitfinex_backfill.time.sleep"
    ) as mock_sleep:
        # Simulate rate limiting on first call, then success
        mock_resp_429 = Mock()
        mock_resp_429.status_code = 429

        mock_resp_ok = Mock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = []

        mock_get.side_effect = [mock_resp_429, mock_resp_ok]

        result = backfill._fetch_bitfinex_candles_page(
            symbol="tBTCUSD",
            timeframe_api="1h",
            start_ms=1000000,
            end_ms=2000000,
            initial_backoff_seconds=2.0,
            max_backoff_seconds=10.0,
            jitter_seconds=0.0,  # No jitter for deterministic testing
            max_retries=3,
        )

        assert result == []
        assert mock_get.call_count == 2
        # Should have slept with initial backoff (2.0 seconds + 0 jitter)
        mock_sleep.assert_called_once()
        sleep_duration = mock_sleep.call_args[0][0]
        assert sleep_duration == 2.0


def test_fetch_bitfinex_candles_page_respects_max_backoff() -> None:
    """Verify that backoff doesn't exceed max_backoff_seconds."""
    with patch("core.market_data.bitfinex_backfill.requests.get") as mock_get, patch(
        "core.market_data.bitfinex_backfill.time.sleep"
    ) as mock_sleep:
        # Simulate rate limiting on all calls
        mock_resp_429 = Mock()
        mock_resp_429.status_code = 429
        mock_get.return_value = mock_resp_429

        with pytest.raises(RuntimeError, match="Bitfinex candle fetch failed"):
            backfill._fetch_bitfinex_candles_page(
                symbol="tBTCUSD",
                timeframe_api="1h",
                start_ms=1000000,
                end_ms=2000000,
                initial_backoff_seconds=1.0,
                max_backoff_seconds=3.0,
                jitter_seconds=0.0,
                max_retries=5,
            )

        # Verify sleep calls respect the max backoff
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        # First: 1.0, Second: 2.0, Third: 3.0 (capped), Fourth: 3.0 (capped), Fifth: 3.0 (capped)
        assert sleep_calls[0] == 1.0
        assert sleep_calls[1] == 2.0
        for call in sleep_calls[2:]:
            assert call <= 3.0


def test_fetch_bitfinex_candles_page_adds_jitter() -> None:
    """Verify that jitter is applied to backoff."""
    with patch("core.market_data.bitfinex_backfill.requests.get") as mock_get, patch(
        "core.market_data.bitfinex_backfill.time.sleep"
    ) as mock_sleep, patch("core.market_data.bitfinex_backfill.random.uniform") as mock_random:
        # Simulate rate limiting on first call, then success
        mock_resp_429 = Mock()
        mock_resp_429.status_code = 429

        mock_resp_ok = Mock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = []

        mock_get.side_effect = [mock_resp_429, mock_resp_ok]
        mock_random.return_value = 0.5  # Fixed jitter value

        result = backfill._fetch_bitfinex_candles_page(
            symbol="tBTCUSD",
            timeframe_api="1h",
            start_ms=1000000,
            end_ms=2000000,
            initial_backoff_seconds=1.0,
            max_backoff_seconds=10.0,
            jitter_seconds=1.0,
            max_retries=3,
        )

        assert result == []
        # Should have called random.uniform with (0, jitter_seconds)
        mock_random.assert_called_once_with(0, 1.0)
        # Should have slept with initial backoff + jitter (1.0 + 0.5)
        mock_sleep.assert_called_once_with(1.5)
