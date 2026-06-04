"""Notification dispatcher for routing alerts to multiple channels."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from core.notifications.telegram import TelegramClient
from core.notifications.discord import DiscordClient

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Configuration for notification channels."""

    telegram_enabled: bool = False
    discord_enabled: bool = False
    telegram_chat_id: Optional[str] = None


Channel = Literal["telegram", "discord", "all"]


class NotificationDispatcher:
    """Dispatcher for routing notifications to multiple channels."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize notification dispatcher.

        Args:
            config: Notification configuration. If not provided, uses defaults from environment.
        """
        self.config = config or NotificationConfig()
        self.telegram = TelegramClient()
        self.discord = DiscordClient()

    async def send_alert(
        self,
        title: str,
        message: str,
        channel: Channel = "all",
        severity: Literal["info", "warning", "error"] = "info",
    ) -> dict[str, bool]:
        """Send alert to configured channels.

        Args:
            title: Alert title
            message: Alert message
            channel: Target channel ("telegram", "discord", or "all")
            severity: Alert severity level

        Returns:
            Dict mapping channel names to success status
        """
        results = {}

        # Determine which channels to send to
        send_telegram = channel in ("telegram", "all") and self.config.telegram_enabled
        send_discord = channel in ("discord", "all") and self.config.discord_enabled

        # Map severity to Discord color
        severity_colors = {
            "info": "green",
            "warning": "yellow",
            "error": "red",
        }
        color = severity_colors.get(severity, "yellow")

        # Send to Telegram
        if send_telegram:
            try:
                success = await self.telegram.send_alert(
                    title=title, message=message, chat_id=self.config.telegram_chat_id
                )
                results["telegram"] = success
                if success:
                    logger.info(f"Telegram notification sent successfully: title='{title}'")
                else:
                    logger.warning(f"Telegram notification failed: title='{title}'")
            except Exception as exc:
                logger.error(
                    f"Telegram notification error: {exc.__class__.__name__}: {str(exc)} | title='{title}'",
                    exc_info=False,  # Don't log full stack trace
                )
                results["telegram"] = False

        # Send to Discord
        if send_discord:
            try:
                success = self.discord.send_alert(title=title, message=message, color=color)
                results["discord"] = success
                if success:
                    logger.info(f"Discord notification sent successfully: title='{title}'")
                else:
                    logger.warning(f"Discord notification failed: title='{title}'")
            except Exception as exc:
                logger.error(
                    f"Discord notification error: {exc.__class__.__name__}: {str(exc)} | title='{title}'",
                    exc_info=False,  # Don't log full stack trace
                )
                results["discord"] = False

        return results

    async def send_price_alert(
        self, symbol: str, price: float, condition: str, channel: Channel = "all"
    ) -> dict[str, bool]:
        """Send price alert notification.

        Args:
            symbol: Trading symbol
            price: Current price
            condition: Alert condition (e.g., "above $50,000")
            channel: Target channel

        Returns:
            Dict mapping channel names to success status
        """
        title = f"🔔 Price Alert: {symbol}"
        message = f"Price is {condition}\nCurrent: ${price:,.2f}"
        return await self.send_alert(title, message, channel=channel, severity="info")

    async def send_trade_alert(
        self, symbol: str, side: str, size: float, price: float, channel: Channel = "all"
    ) -> dict[str, bool]:
        """Send trade execution alert.

        Args:
            symbol: Trading symbol
            side: Trade side ("buy" or "sell")
            size: Trade size
            price: Trade price
            channel: Target channel

        Returns:
            Dict mapping channel names to success status
        """
        emoji = "📈" if side.lower() == "buy" else "📉"
        title = f"{emoji} Trade Executed: {symbol}"
        message = f"Side: {side.upper()}\nSize: {size}\nPrice: ${price:,.2f}"
        return await self.send_alert(title, message, channel=channel, severity="info")
