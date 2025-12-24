"""Tests for multi-timeframe ingestion wrapper script."""

from __future__ import annotations

import os
from unittest.mock import patch

from scripts.ingest_multi_timeframe import DEFAULT_TIMEFRAMES, main, parse_args


def test_parse_args_single_symbol():
    """Test parsing args with single symbol."""
    args = parse_args(["--symbol", "BTCUSD", "--start", "2024-01-01"])
    assert args.symbol == ["BTCUSD"]
    assert args.start == "2024-01-01"
    assert args.resume is False


def test_parse_args_multiple_symbols():
    """Test parsing args with multiple symbols."""
    args = parse_args(["--symbol", "BTCUSD", "--symbol", "ETHUSD", "--resume"])
    assert args.symbol == ["BTCUSD", "ETHUSD"]
    assert args.resume is True


def test_parse_args_custom_timeframes():
    """Test parsing args with custom timeframes."""
    args = parse_args([
        "--symbol", "BTCUSD",
        "--timeframe", "1h",
        "--timeframe", "4h",
        "--resume",
    ])
    assert args.timeframe == ["1h", "4h"]


def test_parse_args_defaults():
    """Test default values for optional args."""
    args = parse_args(["--symbol", "BTCUSD", "--start", "2024-01-01"])
    assert args.exchange == "bitfinex"
    assert args.batch_size == 1000
    assert args.max_retries == 6
    assert args.fail_fast is False


def test_default_timeframes():
    """Test that default timeframes match the spec."""
    expected = ["1m", "5m", "15m", "1h", "4h", "1d"]
    assert DEFAULT_TIMEFRAMES == expected


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
@patch("scripts.ingest_multi_timeframe.backfill_main")
def test_main_success_single_symbol_all_timeframes(mock_backfill):
    """Test successful ingestion of all timeframes for a single symbol."""
    mock_backfill.return_value = 0

    exit_code = main(["--symbol", "BTCUSD", "--start", "2024-01-01"])

    assert exit_code == 0
    assert mock_backfill.call_count == len(DEFAULT_TIMEFRAMES)

    # Verify each timeframe was called
    for i, timeframe in enumerate(DEFAULT_TIMEFRAMES):
        call_args = mock_backfill.call_args_list[i][0][0]
        assert "--symbol" in call_args
        assert "BTCUSD" in call_args
        assert "--timeframe" in call_args
        assert timeframe in call_args


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
@patch("scripts.ingest_multi_timeframe.backfill_main")
def test_main_success_multiple_symbols(mock_backfill):
    """Test successful ingestion for multiple symbols."""
    mock_backfill.return_value = 0

    exit_code = main([
        "--symbol", "BTCUSD",
        "--symbol", "ETHUSD",
        "--timeframe", "1h",
        "--resume",
    ])

    assert exit_code == 0
    assert mock_backfill.call_count == 2  # 2 symbols × 1 timeframe


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
@patch("scripts.ingest_multi_timeframe.backfill_main")
def test_main_partial_failure_continue(mock_backfill):
    """Test that failures are tracked but ingestion continues by default."""
    # First call succeeds, second fails, third succeeds
    mock_backfill.side_effect = [0, 1, 0]

    exit_code = main([
        "--symbol", "BTCUSD",
        "--timeframe", "1h",
        "--timeframe", "4h",
        "--timeframe", "1d",
        "--resume",
    ])

    assert exit_code == 1  # Non-zero because there was a failure
    assert mock_backfill.call_count == 3  # All three were attempted


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
@patch("scripts.ingest_multi_timeframe.backfill_main")
def test_main_fail_fast(mock_backfill):
    """Test fail-fast mode stops on first error."""
    mock_backfill.side_effect = [0, 1, 0]  # Second call fails

    exit_code = main([
        "--symbol", "BTCUSD",
        "--timeframe", "1h",
        "--timeframe", "4h",
        "--timeframe", "1d",
        "--resume",
        "--fail-fast",
    ])

    assert exit_code == 1
    assert mock_backfill.call_count == 2  # Stopped after failure


@patch.dict(os.environ, {}, clear=True)
def test_main_no_database_url():
    """Test error when DATABASE_URL is not set."""
    exit_code = main(["--symbol", "BTCUSD", "--start", "2024-01-01"])
    assert exit_code == 1


def test_main_missing_start_and_resume():
    """Test error when neither --start nor --resume is provided."""
    exit_code = main(["--symbol", "BTCUSD"])
    assert exit_code == 1


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
@patch("scripts.ingest_multi_timeframe.backfill_main")
def test_main_resume_mode(mock_backfill):
    """Test that resume mode passes --resume to backfill."""
    mock_backfill.return_value = 0

    exit_code = main([
        "--symbol", "BTCUSD",
        "--timeframe", "1h",
        "--resume",
    ])

    assert exit_code == 0
    call_args = mock_backfill.call_args[0][0]
    assert "--resume" in call_args
    assert "--start" not in call_args


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"})
@patch("scripts.ingest_multi_timeframe.backfill_main")
def test_main_backfill_mode_with_end(mock_backfill):
    """Test backfill mode with start and end dates."""
    mock_backfill.return_value = 0

    exit_code = main([
        "--symbol", "BTCUSD",
        "--timeframe", "1h",
        "--start", "2024-01-01",
        "--end", "2024-01-31",
    ])

    assert exit_code == 0
    call_args = mock_backfill.call_args[0][0]
    assert "--start" in call_args
    assert "2024-01-01" in call_args
    assert "--end" in call_args
    assert "2024-01-31" in call_args
