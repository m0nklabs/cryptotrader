"""Telegram bot client for notifications."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    """Telegram message to send."""

    text: str
    chat_id: str
    parse_mode: str = "Markdown"  # or "HTML"


class TelegramClient:
    """Telegram bot client for sending notifications.

    Uses python-telegram-bot library (not included by default).
    Install with: pip install python-telegram-bot
    """

    def __init__(self, bot_token: Optional[str] = None, default_chat_id: Optional[str] = None):
        """Initialize Telegram client.

        Args:
            bot_token: Telegram bot token. If not provided, reads from TELEGRAM_BOT_TOKEN env var.
            default_chat_id: Default chat ID to send messages to. If not provided, reads from TELEGRAM_CHAT_ID env var.
        """
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = default_chat_id or os.environ.get("TELEGRAM_CHAT_ID")

        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not configured")

    async def send_message(
        self, text: str, chat_id: Optional[str] = None, parse_mode: str = "Markdown"
    ) -> bool:
        """Send a message via Telegram bot.

        Args:
            text: Message text to send
            chat_id: Chat ID to send to. If not provided, uses default_chat_id
            parse_mode: Parse mode for message formatting ("Markdown" or "HTML")

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.bot_token:
            logger.error("Cannot send Telegram message: bot token not configured")
            return False

        target_chat_id = chat_id or self.default_chat_id
        if not target_chat_id:
            logger.error("Cannot send Telegram message: chat ID not provided")
            return False

        try:
            # Import here to make it optional dependency
            from telegram import Bot

            bot = Bot(token=self.bot_token)
            await bot.send_message(chat_id=target_chat_id, text=text, parse_mode=parse_mode)
            logger.info(f"Telegram message sent to chat {target_chat_id}")
            return True
        except ImportError:
            logger.error("python-telegram-bot library not installed. Install with: pip install python-telegram-bot")
            return False
        except Exception as exc:
            logger.error(f"Failed to send Telegram message: {exc}")
            return False

    async def send_alert(self, title: str, message: str, chat_id: Optional[str] = None) -> bool:
        """Send a formatted alert via Telegram.

        Args:
            title: Alert title
            message: Alert message
            chat_id: Chat ID to send to

        Returns:
            True if alert sent successfully
        """
        # Format alert with bold title
        formatted = f"*{title}*\n\n{message}"
        return await self.send_message(formatted, chat_id=chat_id)
