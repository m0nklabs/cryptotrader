"""Tests for ingestion_report.py script."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ingestion_report import (
    get_ingestion_summary,
    main,
    parse_args,
    validate_db_connection,
    validate_schema,
)


# ========== parse_args tests ==========


def test_parse_args_single_values():
    """Parse args handles single exchange/symbol/timeframe."""
    with patch("sys.argv", ["prog", "--exchange", "bitfinex", "--symbol", "BTCUSD", "--timeframe", "1h"]):
        args = parse_args()
        assert args.exchange == ["bitfinex"]
        assert args.symbol == ["BTCUSD"]
        assert args.timeframe == ["1h"]


def test_parse_args_multiple_values():
    """Parse args handles multiple repeatable values."""
    with patch("sys.argv", [
        "prog",
        "--exchange", "bitfinex", "--exchange", "kraken",
        "--symbol", "BTCUSD", "--symbol", "ETHUSD",
        "--timeframe", "1h", "--timeframe", "4h",
    ]):
        args = parse_args()
        assert args.exchange == ["bitfinex", "kraken"]
        assert args.symbol == ["BTCUSD", "ETHUSD"]
        assert args.timeframe == ["1h", "4h"]


def test_parse_args_no_values():
    """Parse args returns None for missing arguments."""
    with patch("sys.argv", ["prog"]):
        args = parse_args()
        assert args.exchange is None
        assert args.symbol is None
        assert args.timeframe is None


# ========== validate_db_connection tests ==========


def test_validate_db_connection_no_url():
    """Returns False when DATABASE_URL not set."""
    with patch.dict(os.environ, {}, clear=True):
        # Ensure DATABASE_URL is not set
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        
        # Need to reload the module to pick up env change
        with patch("scripts.ingestion_report.DB_URL", None):
            result = validate_db_connection()
            assert result is False


def test_validate_db_connection_success():
    """Returns True when DB connection succeeds."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (1,)
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", return_value=mock_engine):
            result = validate_db_connection()
            assert result is True


def test_validate_db_connection_failure():
    """Returns False when DB connection fails."""
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", side_effect=Exception("Connection failed")):
            result = validate_db_connection()
            assert result is False


# ========== validate_schema tests ==========


def test_validate_schema_table_exists():
    """Returns True when candles table exists."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (True,)
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", return_value=mock_engine):
            result = validate_schema()
            assert result is True


def test_validate_schema_table_missing():
    """Returns False when candles table doesn't exist."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (False,)
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", return_value=mock_engine):
            result = validate_schema()
            assert result is False


def test_validate_schema_error():
    """Returns False when schema check fails."""
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", side_effect=Exception("Query failed")):
            result = validate_schema()
            assert result is False


# ========== get_ingestion_summary tests ==========


def test_get_ingestion_summary_success():
    """Returns summary dict with candle stats."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    test_time = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    mock_result.fetchone.return_value = (True, 1000, test_time)
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", return_value=mock_engine):
            result = get_ingestion_summary("bitfinex", "BTCUSD", "1h")
            
            assert result["schema_ok"] is True
            assert result["candles_count"] == 1000
            assert result["latest_candle_open_time"] == test_time


def test_get_ingestion_summary_no_candles():
    """Returns zero count when no candles found."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (True, 0, None)
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine.connect.return_value = mock_conn
    
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", return_value=mock_engine):
            result = get_ingestion_summary("bitfinex", "BTCUSD", "1h")
            
            assert result["candles_count"] == 0
            assert result["latest_candle_open_time"] is None


def test_get_ingestion_summary_error():
    """Returns empty dict on error."""
    with patch("scripts.ingestion_report.DB_URL", "postgresql://test:test@localhost/test"):
        with patch("scripts.ingestion_report.create_engine", side_effect=Exception("DB error")):
            result = get_ingestion_summary("bitfinex", "BTCUSD", "1h")
            assert result == {}


# ========== main() tests ==========


def test_main_missing_args():
    """Returns 1 when required args missing."""
    with patch("sys.argv", ["prog"]):
        result = main()
        assert result == 1


def test_main_missing_exchange():
    """Returns 1 when exchange missing."""
    with patch("sys.argv", ["prog", "--symbol", "BTCUSD", "--timeframe", "1h"]):
        result = main()
        assert result == 1


def test_main_db_connection_fails():
    """Returns 1 when DB connection fails."""
    with patch("sys.argv", ["prog", "--exchange", "bitfinex", "--symbol", "BTCUSD", "--timeframe", "1h"]):
        with patch("scripts.ingestion_report.validate_db_connection", return_value=False):
            result = main()
            assert result == 1


def test_main_schema_validation_fails():
    """Returns 1 when schema validation fails."""
    with patch("sys.argv", ["prog", "--exchange", "bitfinex", "--symbol", "BTCUSD", "--timeframe", "1h"]):
        with patch("scripts.ingestion_report.validate_db_connection", return_value=True):
            with patch("scripts.ingestion_report.validate_schema", return_value=False):
                result = main()
                assert result == 1


def test_main_success(capsys):
    """Returns 0 and prints summary on success."""
    test_time = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
    mock_summary = {
        "schema_ok": True,
        "candles_count": 500,
        "latest_candle_open_time": test_time,
    }
    
    with patch("sys.argv", ["prog", "--exchange", "bitfinex", "--symbol", "BTCUSD", "--timeframe", "1h"]):
        with patch("scripts.ingestion_report.validate_db_connection", return_value=True):
            with patch("scripts.ingestion_report.validate_schema", return_value=True):
                with patch("scripts.ingestion_report.get_ingestion_summary", return_value=mock_summary):
                    result = main()
                    
                    assert result == 0
                    
                    captured = capsys.readouterr()
                    assert "bitfinex" in captured.out
                    assert "BTCUSD" in captured.out
                    assert "1h" in captured.out
                    assert "500" in captured.out


def test_main_summary_fetch_fails():
    """Returns 1 when summary fetch returns empty."""
    with patch("sys.argv", ["prog", "--exchange", "bitfinex", "--symbol", "BTCUSD", "--timeframe", "1h"]):
        with patch("scripts.ingestion_report.validate_db_connection", return_value=True):
            with patch("scripts.ingestion_report.validate_schema", return_value=True):
                with patch("scripts.ingestion_report.get_ingestion_summary", return_value={}):
                    result = main()
                    assert result == 1
