"""Tests for rate limit tracker."""

import time
from core.ratelimit.tracker import RateLimitTracker, RateLimitInfo


def test_rate_limit_info_properties():
    """Test RateLimitInfo property calculations."""
    reset_time = time.time() + 60  # 60 seconds from now

    info = RateLimitInfo(
        exchange="binance",
        endpoint="trades",
        limit=100,
        remaining=30,
        reset_at=reset_time,
        window_seconds=60,
    )

    assert info.used == 70
    assert info.usage_percent == 70.0
    assert info.reset_in_seconds <= 60
    assert info.reset_in_seconds >= 59
    assert info.status == "warning"  # 70% is in warning range


def test_rate_limit_info_status():
    """Test status indicator thresholds."""
    reset_time = time.time() + 60

    # OK status (< 70%)
    info_ok = RateLimitInfo("exchange", "endpoint", 100, 50, reset_time)
    assert info_ok.status == "ok"

    # Warning status (70-90%)
    info_warning = RateLimitInfo("exchange", "endpoint", 100, 20, reset_time)
    assert info_warning.status == "warning"

    # Critical status (>= 90%)
    info_critical = RateLimitInfo("exchange", "endpoint", 100, 5, reset_time)
    assert info_critical.status == "critical"


def test_tracker_update_and_get():
    """Test updating and retrieving rate limit info."""
    tracker = RateLimitTracker()
    reset_time = time.time() + 60

    tracker.update("binance", "trades", 100, 30, reset_time, 60)

    info = tracker.get("binance", "trades")
    assert info is not None
    assert info.exchange == "binance"
    assert info.endpoint == "trades"
    assert info.limit == 100
    assert info.remaining == 30


def test_tracker_get_all():
    """Test getting all rate limit info."""
    tracker = RateLimitTracker()
    reset_time = time.time() + 60

    tracker.update("binance", "trades", 100, 30, reset_time)
    tracker.update("binance", "orders", 50, 10, reset_time)
    tracker.update("coinbase", "trades", 200, 100, reset_time)

    all_limits = tracker.get_all()
    assert len(all_limits) == 3

    binance_limits = tracker.get_all(exchange="binance")
    assert len(binance_limits) == 2
    assert all(l.exchange == "binance" for l in binance_limits)


def test_tracker_increment_usage():
    """Test manual usage increment."""
    tracker = RateLimitTracker()
    reset_time = time.time() + 60

    tracker.update("binance", "trades", 100, 30, reset_time)
    tracker.increment_usage("binance", "trades")

    info = tracker.get("binance", "trades")
    assert info.remaining == 29


def test_tracker_should_throttle():
    """Test throttling decision based on usage."""
    tracker = RateLimitTracker()
    reset_time = time.time() + 60

    # 70% usage, default threshold is 90%
    tracker.update("binance", "trades", 100, 30, reset_time)
    assert not tracker.should_throttle("binance", "trades")

    # 95% usage, should throttle
    tracker.update("binance", "orders", 100, 5, reset_time)
    assert tracker.should_throttle("binance", "orders")

    # Custom threshold 80%
    assert tracker.should_throttle("binance", "trades", threshold=0.7)


def test_tracker_clear_expired():
    """Test clearing expired rate limit entries."""
    tracker = RateLimitTracker()

    # Add expired entry
    expired_time = time.time() - 10
    tracker.update("binance", "trades", 100, 30, expired_time)

    # Add valid entry
    valid_time = time.time() + 60
    tracker.update("binance", "orders", 100, 50, valid_time)

    tracker.clear_expired()

    # Expired entry should be removed
    assert tracker.get("binance", "trades") is None
    assert tracker.get("binance", "orders") is not None
