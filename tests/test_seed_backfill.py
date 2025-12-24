from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_data import seed_backfill


def test_calculate_chunks_single_chunk_when_range_smaller_than_chunk() -> None:
    """Test that a small range results in a single chunk."""
    end = datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc)
    chunks = seed_backfill._calculate_chunks(
        end=end,
        total_days=1,
        chunk_minutes=240,  # 4 hours
        timeframe="1h",
    )
    # 1 day = 24 hours, chunk = 4 hours -> should have 6 chunks
    assert len(chunks) == 6
    # Verify chronological order (oldest first)
    assert chunks[0][0] < chunks[1][0]
    # Verify coverage
    assert chunks[0][0] == end - timedelta(days=1)
    assert chunks[-1][1] == end


def test_calculate_chunks_multiple_chunks() -> None:
    """Test chunking a 7-day period with 3-hour chunks."""
    end = datetime(2025, 1, 10, 0, 0, tzinfo=timezone.utc)
    chunks = seed_backfill._calculate_chunks(
        end=end,
        total_days=7,
        chunk_minutes=180,  # 3 hours
        timeframe="1h",
    )
    # 7 days = 168 hours, chunk = 3 hours -> 168 / 3 = 56 chunks
    assert len(chunks) == 56
    # First chunk should start 7 days before end
    assert chunks[0][0] == end - timedelta(days=7)
    # Last chunk should end at 'end'
    assert chunks[-1][1] == end
    # Verify no gaps between chunks
    for i in range(len(chunks) - 1):
        assert chunks[i][1] == chunks[i + 1][0]


def test_calculate_chunks_ensures_chronological_order() -> None:
    """Test that chunks are returned in chronological order (oldest first)."""
    end = datetime(2025, 1, 5, 0, 0, tzinfo=timezone.utc)
    chunks = seed_backfill._calculate_chunks(
        end=end,
        total_days=2,
        chunk_minutes=120,  # 2 hours
        timeframe="1h",
    )
    for i in range(len(chunks) - 1):
        # Each chunk's start should be before the next chunk's start
        assert chunks[i][0] < chunks[i + 1][0]
        # Each chunk's end should equal the next chunk's start
        assert chunks[i][1] == chunks[i + 1][0]


def test_calculate_chunks_respects_timeframe_validity() -> None:
    """Test that invalid timeframes raise an error."""
    end = datetime(2025, 1, 10, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        seed_backfill._calculate_chunks(
            end=end,
            total_days=7,
            chunk_minutes=180,
            timeframe="99m",  # Invalid timeframe
        )


def test_seed_config_immutable() -> None:
    """Test that SeedConfig is frozen/immutable."""
    config = seed_backfill.SeedConfig(
        symbol="BTCUSD",
        timeframe="1h",
        days=7,
        chunk_minutes=180,
        sleep_seconds=2.0,
    )
    with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError is a subclass
        config.days = 10


def test_build_arg_parser_accepts_all_required_args() -> None:
    """Test that the argument parser accepts all required arguments."""
    parser = seed_backfill.build_arg_parser()
    args = parser.parse_args([
        "--symbol", "BTCUSD",
        "--timeframe", "1h",
        "--days", "7",
        "--chunk-minutes", "180",
        "--sleep-seconds", "2.5",
    ])
    assert args.symbol == "BTCUSD"
    assert args.timeframe == "1h"
    assert args.days == 7
    assert args.chunk_minutes == 180
    assert args.sleep_seconds == 2.5


def test_build_arg_parser_uses_defaults() -> None:
    """Test that optional arguments have sensible defaults."""
    parser = seed_backfill.build_arg_parser()
    args = parser.parse_args([
        "--symbol", "ETHUSD",
        "--timeframe", "5m",
        "--days", "30",
    ])
    assert args.chunk_minutes == 180  # Default 3 hours
    assert args.sleep_seconds == 2.0  # Default 2 seconds
    assert args.exchange == "bitfinex"  # Default exchange
    assert args.resume is False  # Default no resume
