"""Alert notification dispatcher."""

from __future__ import annotations

import logging
from typing import Optional

from core.alerts.models import Alert, AlertHistory
from core.notifications import NotificationDispatcher, NotificationConfig

logger = logging.getLogger(__name__)


class AlertNotifier:
    """Sends notifications when alerts are triggered."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize the alert notifier.

        Args:
            config: Notification configuration. Uses defaults if not provided.
        """
        self.dispatcher = NotificationDispatcher(config)

    async def send_alert_notification(
        self,
        alert: Alert,
        history: AlertHistory,
    ) -> dict[str, bool]:
        """Send notification for a triggered alert.

        Args:
            alert: Alert that was triggered
            history: History entry with trigger details

        Returns:
            Dict mapping channel names to success status
        """
        title = f"🔔 Alert: {alert.symbol} on {alert.exchange}"
        
        # Format message with alert details
        message = (
            f"{history.message}\n"
            f"Symbol: {alert.symbol}\n"
            f"Exchange: {alert.exchange}\n"
            f"Timeframe: {alert.timeframe}\n"
            f"Current Price: ${history.price:.2f}\n"
            f"Triggered at: {history.triggered_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        # Determine severity based on alert type
        severity = "warning"
        if alert.condition.type in ("price_above", "price_below"):
            severity = "info"
        elif alert.condition.type in ("rsi_overbought", "rsi_oversold", "macd_cross_up", "macd_cross_down"):
            severity = "warning"

        try:
            results = await self.dispatcher.send_alert(
                title=title,
                message=message,
                channel="all",
                severity=severity,
            )
            logger.info(f"Alert notification sent for alert {alert.id}: {results}")
            return results
        except Exception as e:
            logger.error(f"Failed to send alert notification for alert {alert.id}: {e}", exc_info=True)
            return {}
