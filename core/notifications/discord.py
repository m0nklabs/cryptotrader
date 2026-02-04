"""Discord webhook client for notifications."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
import logging

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

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
        self._client: Optional[httpx.AsyncClient] = None if HTTPX_AVAILABLE else None

        if not self.webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not configured")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not available, install with: pip install httpx")
        
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    def send_message(
        self,
        content: str,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> bool:
        """Send a message via Discord webhook (sync version for backward compatibility).

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
            import requests
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Discord message sent successfully")
            return True
        except Exception as exc:
            logger.error(f"Failed to send Discord message: {exc}")
            return False

    async def send_message_async(
        self,
        content: str,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> bool:
        """Send a message via Discord webhook (async version, non-blocking).

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
            if HTTPX_AVAILABLE:
                client = await self._get_client()
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                )
                response.raise_for_status()
            else:
                # Fallback to sync requests in thread
                import asyncio
                import requests
                response = await asyncio.to_thread(
                    requests.post,
                    self.webhook_url,
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
            
            logger.info("Discord message sent successfully")
            return True
        except Exception as exc:
            logger.error(f"Failed to send Discord message: {exc}")
            return False

    def send_alert(self, title: str, message: str, color: str = "yellow") -> bool:
        """Send a formatted alert via Discord embed (sync version for backward compatibility).

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
            import requests
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Discord alert sent successfully")
            return True
        except Exception as exc:
            logger.error(f"Failed to send Discord alert: {exc}")
            return False

    async def send_alert_async(self, title: str, message: str, color: str = "yellow") -> bool:
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
            if HTTPX_AVAILABLE:
                client = await self._get_client()
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                )
                response.raise_for_status()
            else:
                # Fallback to sync requests in thread
                import asyncio
                import requests
                response = await asyncio.to_thread(
                    requests.post,
                    self.webhook_url,
                    json=payload,
                    timeout=10,
                )
                response.raise_for_status()
            
            logger.info("Discord alert sent successfully")
            return True
        except Exception as exc:
            logger.error(f"Failed to send Discord alert: {exc}")
            return False
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
