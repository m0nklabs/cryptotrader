"""API routes for notifications."""

from __future__ import annotations

from typing import Literal, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.notifications import NotificationDispatcher, NotificationConfig

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SendAlertRequest(BaseModel):
    """Request to send an alert."""

    title: str
    message: str
    channel: Literal["telegram", "discord", "all"] = "all"
    severity: Literal["info", "warning", "error"] = "info"


class NotificationSettingsRequest(BaseModel):
    """Request to update notification settings."""

    telegram_enabled: bool = False
    discord_enabled: bool = False
    telegram_chat_id: Optional[str] = None


# Global notification config (in-memory for now)
_notification_config = NotificationConfig()


@router.post("/send")
async def send_notification(request: SendAlertRequest):
    """Send a notification to configured channels.

    This is primarily for testing. Production alerts should be triggered by events.
    """
    dispatcher = NotificationDispatcher(config=_notification_config)
    results = await dispatcher.send_alert(
        title=request.title,
        message=request.message,
        channel=request.channel,
        severity=request.severity,
    )

    # Check if any notification was sent
    if not results:
        raise HTTPException(status_code=400, detail="No notification channels configured")

    success_count = sum(1 for v in results.values() if v)

    return {
        "success": success_count > 0,
        "results": results,
        "message": f"Sent to {success_count}/{len(results)} channels",
    }


@router.get("/settings")
async def get_notification_settings():
    """Get current notification settings."""
    return {
        "telegram_enabled": _notification_config.telegram_enabled,
        "discord_enabled": _notification_config.discord_enabled,
        "telegram_configured": _notification_config.telegram_chat_id is not None,
    }


@router.post("/settings")
async def update_notification_settings(request: NotificationSettingsRequest):
    """Update notification settings."""
    global _notification_config

    # Preserve existing telegram_chat_id if the request does not provide one
    effective_telegram_chat_id = (
        request.telegram_chat_id if request.telegram_chat_id is not None else _notification_config.telegram_chat_id
    )

    _notification_config = NotificationConfig(
        telegram_enabled=request.telegram_enabled,
        discord_enabled=request.discord_enabled,
        telegram_chat_id=effective_telegram_chat_id,
    )

    return {
        "success": True,
        "settings": {
            "telegram_enabled": _notification_config.telegram_enabled,
            "discord_enabled": _notification_config.discord_enabled,
        },
    }


@router.post("/test/{channel}")
async def test_notification(channel: Literal["telegram", "discord"]):
    """Send a test notification to verify configuration."""
    dispatcher = NotificationDispatcher(config=_notification_config)

    results = await dispatcher.send_alert(
        title="🧪 Test Notification",
        message="This is a test message from cryptotrader. If you received this, your notifications are working!",
        channel=channel,
        severity="info",
    )

    if not results or not results.get(channel):
        raise HTTPException(status_code=500, detail=f"Failed to send test notification to {channel}")

    return {
        "success": True,
        "message": f"Test notification sent to {channel}",
    }
