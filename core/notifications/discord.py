"""Discord webhook client for notifications."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
import logging
import requests

logger = logging.getLogger(__name__)


@dataclass
class DiscordMessage:
    """Discord message to send."""

    content: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class DiscordClient:
    """Discord webhook client for sending notifications."""

    def __init__(self, webhook_url: Optional[str] = None):
        """Initialize Discord client.

        Args:
            webhook_url: Discord webhook URL. If not provided, reads from DISCORD_WEBHOOK_URL env var.
        """
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")

        if not self.webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not configured")

    def send_message(
        self,
        content: str,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> bool:
        """Send a message via Discord webhook.

        Args:
            content: Message content to send
            username: Override webhook username (optional)
            avatar_url: Override webhook avatar (optional)

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.webhook_url:
            logger.error("Cannot send Discord message: webhook URL not configured")
            return False

        payload = {"content": content}
        if username:
            payload["username"] = username
        if avatar_url:
            payload["avatar_url"] = avatar_url

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Discord message sent successfully")
            return True
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to send Discord message: {exc}")
            return False

    def send_alert(self, title: str, message: str, color: str = "yellow") -> bool:
        """Send a formatted alert via Discord embed.

        Args:
            title: Alert title
            message: Alert message
            color: Alert color ("green", "yellow", "red")

        Returns:
            True if alert sent successfully
        """
        if not self.webhook_url:
            logger.error("Cannot send Discord alert: webhook URL not configured")
            return False

        # Map color names to Discord embed colors
        color_map = {
            "green": 0x00FF00,
            "yellow": 0xFFFF00,
            "red": 0xFF0000,
        }
        embed_color = color_map.get(color, 0xFFFF00)

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "color": embed_color,
                }
            ]
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Discord alert sent successfully")
            return True
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to send Discord alert: {exc}")
            return False
