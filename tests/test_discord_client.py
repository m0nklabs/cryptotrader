"""Tests for Discord client."""

from unittest.mock import patch, MagicMock
from core.notifications.discord import DiscordClient


def test_discord_client_init():
    """Test DiscordClient initialization."""
    client = DiscordClient(webhook_url="https://discord.com/webhook/test")

    assert client.webhook_url == "https://discord.com/webhook/test"


def test_discord_client_no_webhook():
    """Test DiscordClient without webhook URL."""
    with patch.dict("os.environ", {}, clear=True):
        client = DiscordClient()

    assert client.webhook_url is None


def test_send_message_no_webhook():
    """Test sending message without webhook configured."""
    client = DiscordClient()
    result = client.send_message("Test message")

    assert result is False


def test_send_message_success():
    """Test sending message successfully."""
    client = DiscordClient(webhook_url="https://discord.com/webhook/test")

    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 204

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = client.send_message("Test message")

    assert result is True
    mock_post.assert_called_once()


def test_send_message_failure():
    """Test sending message with error."""
    client = DiscordClient(webhook_url="https://discord.com/webhook/test")

    # Mock failed response
    import requests

    with patch(
        "requests.post", side_effect=requests.exceptions.RequestException("Network error")
    ):
        result = client.send_message("Test message")

    assert result is False


def test_send_alert_colors():
    """Test sending alert with different colors."""
    client = DiscordClient(webhook_url="https://discord.com/webhook/test")

    mock_response = MagicMock()
    mock_response.status_code = 204

    with patch("requests.post", return_value=mock_response) as mock_post:
        # Test green
        client.send_alert("Title", "Message", color="green")
        call_args = mock_post.call_args[1]["json"]
        assert call_args["embeds"][0]["color"] == 0x00FF00

        # Test yellow
        client.send_alert("Title", "Message", color="yellow")
        call_args = mock_post.call_args[1]["json"]
        assert call_args["embeds"][0]["color"] == 0xFFFF00

        # Test red
        client.send_alert("Title", "Message", color="red")
        call_args = mock_post.call_args[1]["json"]
        assert call_args["embeds"][0]["color"] == 0xFF0000
