"""Tests for Telegram client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.notifications.telegram import TelegramClient


def test_telegram_client_init():
    """Test TelegramClient initialization."""
    client = TelegramClient(bot_token="test_token", default_chat_id="123456")

    assert client.bot_token == "test_token"
    assert client.default_chat_id == "123456"


def test_telegram_client_no_token():
    """Test TelegramClient without token."""
    with patch.dict("os.environ", {}, clear=True):
        client = TelegramClient()

    assert client.bot_token is None


@pytest.mark.asyncio
async def test_send_message_no_token():
    """Test sending message without token configured."""
    client = TelegramClient()
    result = await client.send_message("Test message", chat_id="123456")

    assert result is False


@pytest.mark.asyncio
async def test_send_message_no_chat_id():
    """Test sending message without chat ID."""
    client = TelegramClient(bot_token="test_token")
    result = await client.send_message("Test message")

    assert result is False


@pytest.mark.asyncio
async def test_send_alert():
    """Test sending formatted alert (without telegram library)."""
    client = TelegramClient(bot_token="test_token", default_chat_id="123456")

    # Without telegram library, this should return False gracefully
    result = await client.send_alert("Alert Title", "Alert message")

    # Without telegram library installed, we expect False
    assert result is False
