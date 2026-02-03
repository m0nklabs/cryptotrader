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
    """Test sending formatted alert."""
    client = TelegramClient(bot_token="test_token", default_chat_id="123456")

    # Mock the Bot to avoid ImportError and actual API call
    with patch("core.notifications.telegram.Bot") as mock_bot:
        mock_instance = AsyncMock()
        mock_bot.return_value = mock_instance

        result = await client.send_alert("Alert Title", "Alert message")

    # With mocking, we expect success
    assert result is True
