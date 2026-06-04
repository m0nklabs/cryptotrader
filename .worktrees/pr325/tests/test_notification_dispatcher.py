"""Tests for notification dispatcher."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from core.notifications.dispatcher import NotificationDispatcher, NotificationConfig


@pytest.mark.asyncio
async def test_dispatcher_send_alert_telegram():
    """Test sending alert to Telegram only."""
    config = NotificationConfig(
        telegram_enabled=True,
        discord_enabled=False,
        telegram_chat_id="123456",
    )
    dispatcher = NotificationDispatcher(config)

    # Mock clients
    dispatcher.telegram.send_alert = AsyncMock(return_value=True)
    dispatcher.discord.send_alert = MagicMock(return_value=True)

    results = await dispatcher.send_alert(
        title="Test Alert",
        message="Test message",
        channel="telegram",
        severity="info",
    )

    assert results == {"telegram": True}
    dispatcher.telegram.send_alert.assert_called_once_with(
        title="Test Alert",
        message="Test message",
        chat_id="123456",
    )
    dispatcher.discord.send_alert.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_send_alert_discord():
    """Test sending alert to Discord only."""
    config = NotificationConfig(
        telegram_enabled=False,
        discord_enabled=True,
    )
    dispatcher = NotificationDispatcher(config)

    # Mock clients
    dispatcher.telegram.send_alert = AsyncMock(return_value=True)
    dispatcher.discord.send_alert = MagicMock(return_value=True)

    results = await dispatcher.send_alert(
        title="Test Alert",
        message="Test message",
        channel="discord",
        severity="warning",
    )

    assert results == {"discord": True}
    dispatcher.discord.send_alert.assert_called_once_with(
        title="Test Alert",
        message="Test message",
        color="yellow",
    )
    dispatcher.telegram.send_alert.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_send_alert_all_channels():
    """Test sending alert to all channels."""
    config = NotificationConfig(
        telegram_enabled=True,
        discord_enabled=True,
        telegram_chat_id="123456",
    )
    dispatcher = NotificationDispatcher(config)

    # Mock clients
    dispatcher.telegram.send_alert = AsyncMock(return_value=True)
    dispatcher.discord.send_alert = MagicMock(return_value=True)

    results = await dispatcher.send_alert(
        title="Test Alert",
        message="Test message",
        channel="all",
        severity="error",
    )

    assert results == {"telegram": True, "discord": True}
    dispatcher.telegram.send_alert.assert_called_once()
    dispatcher.discord.send_alert.assert_called_once_with(
        title="Test Alert",
        message="Test message",
        color="red",
    )


@pytest.mark.asyncio
async def test_dispatcher_send_price_alert():
    """Test sending price alert."""
    config = NotificationConfig(
        telegram_enabled=True,
        discord_enabled=False,
        telegram_chat_id="123456",
    )
    dispatcher = NotificationDispatcher(config)
    dispatcher.telegram.send_alert = AsyncMock(return_value=True)

    results = await dispatcher.send_price_alert(
        symbol="BTCUSD",
        price=50000.50,
        condition="above $50,000",
        channel="telegram",
    )

    assert results == {"telegram": True}
    call_args = dispatcher.telegram.send_alert.call_args
    assert "BTCUSD" in call_args[1]["title"]
    assert "50,000.50" in call_args[1]["message"]
    assert "above $50,000" in call_args[1]["message"]


@pytest.mark.asyncio
async def test_dispatcher_send_trade_alert():
    """Test sending trade alert."""
    config = NotificationConfig(
        discord_enabled=True,
        telegram_enabled=False,
    )
    dispatcher = NotificationDispatcher(config)
    dispatcher.discord.send_alert = MagicMock(return_value=True)

    results = await dispatcher.send_trade_alert(
        symbol="ETHUSD",
        side="sell",
        size=1.5,
        price=3000.00,
        channel="discord",
    )

    assert results == {"discord": True}
    call_args = dispatcher.discord.send_alert.call_args
    assert "ETHUSD" in call_args[1]["title"]
    assert "SELL" in call_args[1]["message"]
    assert "1.5" in call_args[1]["message"]


@pytest.mark.asyncio
async def test_dispatcher_severity_color_mapping():
    """Test severity to color mapping."""
    config = NotificationConfig(discord_enabled=True)
    dispatcher = NotificationDispatcher(config)
    dispatcher.discord.send_alert = MagicMock(return_value=True)

    # Test info -> green
    await dispatcher.send_alert("Title", "Message", channel="discord", severity="info")
    assert dispatcher.discord.send_alert.call_args[1]["color"] == "green"

    # Test warning -> yellow
    await dispatcher.send_alert("Title", "Message", channel="discord", severity="warning")
    assert dispatcher.discord.send_alert.call_args[1]["color"] == "yellow"

    # Test error -> red
    await dispatcher.send_alert("Title", "Message", channel="discord", severity="error")
    assert dispatcher.discord.send_alert.call_args[1]["color"] == "red"
