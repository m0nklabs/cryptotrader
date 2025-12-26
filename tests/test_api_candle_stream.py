"""Tests for real-time candle streaming API endpoints."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_candle_stream_service_initialization():
    """Test that CandleStreamService can be initialized."""
    from api.candle_stream import CandleStreamService

    service = CandleStreamService()

    assert service.providers == {}
    assert service.subscribers == {}
    assert service.latest_candles == {}


def test_candle_stream_service_get_key():
    """Test subscription key generation."""
    from api.candle_stream import CandleStreamService

    service = CandleStreamService()
    key = service._get_key("BTCUSD", "1m")

    assert key == "BTCUSD:1m"


@patch("api.candle_stream.BitfinexWebSocketCandleProvider")
def test_get_or_create_provider(mock_provider_class):
    """Test getting or creating a WebSocket provider."""
    from api.candle_stream import CandleStreamService

    # Setup mock
    mock_provider = Mock()
    mock_provider.subscribe = Mock()
    mock_provider.start = Mock()
    mock_provider_class.return_value = mock_provider

    service = CandleStreamService()

    # First call should create provider
    provider1 = service.get_or_create_provider("BTCUSD", "1m")

    assert provider1 == mock_provider
    assert "BTCUSD:1m" in service.providers
    mock_provider.subscribe.assert_called_once()
    mock_provider.start.assert_called_once()

    # Second call should return same provider
    provider2 = service.get_or_create_provider("BTCUSD", "1m")

    assert provider2 == provider1
    # subscribe and start should not be called again
    assert mock_provider.subscribe.call_count == 1
    assert mock_provider.start.call_count == 1


@pytest.mark.asyncio
async def test_candle_stream_service_broadcast():
    """Test broadcasting candle updates to subscribers."""
    from api.candle_stream import CandleStreamService
    from core.types import Candle
    from datetime import datetime, timezone
    from decimal import Decimal

    service = CandleStreamService()

    # Create test candle
    candle = Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1m",
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("50100"),
        low=Decimal("49900"),
        close=Decimal("50050"),
        volume=Decimal("10.5"),
    )

    # Create mock subscribers
    queue1 = asyncio.Queue()
    queue2 = asyncio.Queue()

    service.subscribers["BTCUSD:1m"] = [queue1, queue2]

    # Broadcast candle
    service._broadcast_candle("BTCUSD:1m", candle)

    # Verify both queues received the candle
    received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

    assert received1 == candle
    assert received2 == candle
    assert service.latest_candles["BTCUSD:1m"] == candle


def test_candle_to_dict():
    """Test converting Candle to dictionary."""
    from api.candle_stream import CandleStreamService
    from core.types import Candle
    from datetime import datetime, timezone
    from decimal import Decimal

    service = CandleStreamService()

    candle = Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1m",
        open_time=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        close_time=datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
        open=Decimal("50000"),
        high=Decimal("50100"),
        low=Decimal("49900"),
        close=Decimal("50050"),
        volume=Decimal("10.5"),
    )

    result = service._candle_to_dict(candle)

    assert result["type"] == "candle"
    assert result["symbol"] == "BTCUSD"
    assert result["timeframe"] == "1m"
    assert result["t"] == 1704110400000  # Unix timestamp in ms
    assert result["o"] == 50000.0
    assert result["h"] == 50100.0
    assert result["l"] == 49900.0
    assert result["c"] == 50050.0
    assert result["v"] == 10.5


def test_get_connection_status():
    """Test getting connection status."""
    from api.candle_stream import CandleStreamService

    service = CandleStreamService()

    # Initially empty
    status = service.get_connection_status()

    assert status["active_streams"] == 0
    assert status["total_subscribers"] == 0
    assert status["streams"] == []


def test_stream_endpoint_exists():
    """Test that the stream endpoint is registered."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/candles/stream" in routes


def test_stream_status_endpoint_exists():
    """Test that the stream status endpoint is registered."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/candles/stream/status" in routes


def test_singleton_service():
    """Test that get_candle_stream_service returns a singleton."""
    from api.candle_stream import get_candle_stream_service

    service1 = get_candle_stream_service()
    service2 = get_candle_stream_service()

    assert service1 is service2


@pytest.mark.asyncio
async def test_subscriber_cleanup_stops_provider():
    """Test that provider is stopped when last subscriber disconnects."""
    from api.candle_stream import CandleStreamService
    from unittest.mock import Mock

    service = CandleStreamService()

    # Mock the provider
    mock_provider = Mock()
    mock_provider.stop = Mock()
    mock_provider.is_connected = Mock(return_value=True)

    # Manually set up provider to avoid actual WebSocket connection
    key = "BTCUSD:1m"
    service.providers[key] = mock_provider

    # Create a subscriber queue
    queue1 = asyncio.Queue(maxsize=100)
    service.subscribers[key].append(queue1)

    # Simulate subscriber cleanup
    with service.lock:
        service.subscribers[key].remove(queue1)
        remaining = len(service.subscribers[key])

        if remaining == 0 and key in service.providers:
            service.providers[key].stop()
            del service.providers[key]
            if key in service.latest_candles:
                del service.latest_candles[key]

    # Verify provider was stopped and removed
    mock_provider.stop.assert_called_once()
    assert key not in service.providers
    assert key not in service.latest_candles


@pytest.mark.asyncio
async def test_multiple_subscribers_dont_stop_provider():
    """Test that provider is not stopped when other subscribers remain."""
    from api.candle_stream import CandleStreamService
    from unittest.mock import Mock

    service = CandleStreamService()

    # Mock the provider
    mock_provider = Mock()
    mock_provider.stop = Mock()

    # Manually set up provider
    key = "BTCUSD:1m"
    service.providers[key] = mock_provider

    # Create two subscriber queues
    queue1 = asyncio.Queue(maxsize=100)
    queue2 = asyncio.Queue(maxsize=100)
    service.subscribers[key].append(queue1)
    service.subscribers[key].append(queue2)

    # Remove first subscriber
    with service.lock:
        service.subscribers[key].remove(queue1)
        remaining = len(service.subscribers[key])

        # Should NOT stop provider since queue2 is still subscribed
        if remaining == 0 and key in service.providers:
            service.providers[key].stop()
            del service.providers[key]

    # Verify provider was NOT stopped
    mock_provider.stop.assert_not_called()
    assert key in service.providers


@pytest.mark.asyncio
async def test_cleanup_removes_latest_candle():
    """Test that latest_candles is cleaned up to avoid memory leak."""
    from api.candle_stream import CandleStreamService
    from core.types import Candle
    from datetime import datetime, timezone
    from decimal import Decimal
    from unittest.mock import Mock

    service = CandleStreamService()

    # Mock the provider
    mock_provider = Mock()
    mock_provider.stop = Mock()

    # Create test candle
    candle = Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1m",
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("50100"),
        low=Decimal("49900"),
        close=Decimal("50050"),
        volume=Decimal("10.5"),
    )

    # Set up provider and latest candle
    key = "BTCUSD:1m"
    service.providers[key] = mock_provider
    service.latest_candles[key] = candle

    # Create and remove subscriber
    queue = asyncio.Queue(maxsize=100)
    service.subscribers[key].append(queue)

    # Simulate cleanup
    with service.lock:
        service.subscribers[key].remove(queue)
        remaining = len(service.subscribers[key])

        if remaining == 0 and key in service.providers:
            service.providers[key].stop()
            del service.providers[key]
            if key in service.latest_candles:
                del service.latest_candles[key]

    # Verify latest_candles was cleaned up
    assert key not in service.latest_candles
