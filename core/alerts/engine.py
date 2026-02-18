"""Alert evaluation engine for checking conditions against market data."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from core.alerts.models import Alert, AlertHistory, AlertType, ComparisonOperator
from core.indicators.rsi import calculate_rsi
from core.indicators.macd import calculate_macd

logger = logging.getLogger(__name__)


class AlertEngine:
    """Engine for evaluating alert conditions against market data."""

    def __init__(self):
        """Initialize the alert engine."""
        self._previous_states: dict[int, dict] = {}  # Track previous values for crossover detection

    async def evaluate_alert(
        self,
        alert: Alert,
        current_price: float,
        ohlcv_data: Optional[pd.DataFrame] = None,
    ) -> tuple[bool, Optional[AlertHistory]]:
        """Evaluate an alert condition against current market data.

        Args:
            alert: Alert to evaluate
            current_price: Current price of the symbol
            ohlcv_data: Optional OHLCV DataFrame for indicator calculations

        Returns:
            Tuple of (triggered: bool, history_entry: Optional[AlertHistory])
        """
        if not alert.enabled:
            return False, None

        alert_type = alert.condition.type
        threshold = alert.condition.value
        operator = alert.condition.operator

        try:
            # Price-based alerts
            if alert_type == "price_above":
                triggered = self._check_price_condition(
                    alert.id, current_price, threshold, "above", operator
                )
                if triggered:
                    return True, self._create_history(
                        alert,
                        current_price,
                        current_price,
                        f"Price {current_price:.2f} crossed above {threshold:.2f}",
                    )

            elif alert_type == "price_below":
                triggered = self._check_price_condition(
                    alert.id, current_price, threshold, "below", operator
                )
                if triggered:
                    return True, self._create_history(
                        alert,
                        current_price,
                        current_price,
                        f"Price {current_price:.2f} crossed below {threshold:.2f}",
                    )

            # Indicator-based alerts require OHLCV data
            if ohlcv_data is None or len(ohlcv_data) < 50:
                logger.debug(f"Insufficient data for indicator alert {alert.id}")
                return False, None

            # RSI alerts
            if alert_type == "rsi_overbought":
                period = alert.condition.indicator_params.get("period", 14) if alert.condition.indicator_params else 14
                rsi = calculate_rsi(ohlcv_data, period=period)
                if rsi.empty:
                    return False, None
                current_rsi = rsi.iloc[-1]
                triggered = self._check_price_condition(
                    alert.id, current_rsi, threshold, "above", operator
                )
                if triggered:
                    return True, self._create_history(
                        alert,
                        current_rsi,
                        current_price,
                        f"RSI {current_rsi:.2f} crossed above {threshold:.2f} (overbought)",
                    )

            elif alert_type == "rsi_oversold":
                period = alert.condition.indicator_params.get("period", 14) if alert.condition.indicator_params else 14
                rsi = calculate_rsi(ohlcv_data, period=period)
                if rsi.empty:
                    return False, None
                current_rsi = rsi.iloc[-1]
                triggered = self._check_price_condition(
                    alert.id, current_rsi, threshold, "below", operator
                )
                if triggered:
                    return True, self._create_history(
                        alert,
                        current_rsi,
                        current_price,
                        f"RSI {current_rsi:.2f} crossed below {threshold:.2f} (oversold)",
                    )

            # MACD crossover alerts
            elif alert_type == "macd_cross_up":
                macd_result = calculate_macd(ohlcv_data)
                if macd_result.empty:
                    return False, None
                
                # Check if MACD line crossed above signal line
                macd_line = macd_result["macd"].iloc[-1]
                signal_line = macd_result["signal"].iloc[-1]
                prev_macd = macd_result["macd"].iloc[-2] if len(macd_result) > 1 else macd_line
                prev_signal = macd_result["signal"].iloc[-2] if len(macd_result) > 1 else signal_line
                
                triggered = prev_macd <= prev_signal and macd_line > signal_line
                if triggered:
                    return True, self._create_history(
                        alert,
                        macd_line - signal_line,
                        current_price,
                        f"MACD bullish crossover: MACD {macd_line:.4f} crossed above signal {signal_line:.4f}",
                    )

            elif alert_type == "macd_cross_down":
                macd_result = calculate_macd(ohlcv_data)
                if macd_result.empty:
                    return False, None
                
                # Check if MACD line crossed below signal line
                macd_line = macd_result["macd"].iloc[-1]
                signal_line = macd_result["signal"].iloc[-1]
                prev_macd = macd_result["macd"].iloc[-2] if len(macd_result) > 1 else macd_line
                prev_signal = macd_result["signal"].iloc[-2] if len(macd_result) > 1 else signal_line
                
                triggered = prev_macd >= prev_signal and macd_line < signal_line
                if triggered:
                    return True, self._create_history(
                        alert,
                        macd_line - signal_line,
                        current_price,
                        f"MACD bearish crossover: MACD {macd_line:.4f} crossed below signal {signal_line:.4f}",
                    )

        except Exception as e:
            logger.error(f"Error evaluating alert {alert.id}: {e}", exc_info=True)
            return False, None

        return False, None

    def _check_price_condition(
        self,
        alert_id: Optional[int],
        current_value: float,
        threshold: float,
        direction: str,
        operator: ComparisonOperator,
    ) -> bool:
        """Check if a price condition is met.

        Args:
            alert_id: Alert ID for tracking state
            current_value: Current value (price, RSI, etc.)
            threshold: Threshold to compare against
            direction: "above" or "below"
            operator: Comparison operator

        Returns:
            True if condition is met
        """
        # For simple comparisons
        if operator in ("above", "below"):
            if direction == "above":
                return current_value > threshold
            else:
                return current_value < threshold

        # For crossover detection, track previous state
        if operator in ("crosses_above", "crosses_below"):
            if alert_id is None:
                return False

            previous_value = self._previous_states.get(alert_id, {}).get("value")
            self._previous_states[alert_id] = {"value": current_value}

            if previous_value is None:
                return False

            if operator == "crosses_above":
                return previous_value <= threshold < current_value
            else:  # crosses_below
                return previous_value >= threshold > current_value

        return False

    def _create_history(
        self,
        alert: Alert,
        trigger_value: float,
        price: float,
        message: str,
    ) -> AlertHistory:
        """Create an alert history entry.

        Args:
            alert: Alert that was triggered
            trigger_value: Value that triggered the alert
            price: Current price
            message: Alert message

        Returns:
            AlertHistory entry
        """
        from datetime import datetime

        return AlertHistory(
            alert_id=alert.id or 0,
            triggered_at=datetime.utcnow(),
            trigger_value=trigger_value,
            price=price,
            message=message,
        )

    def reset_state(self, alert_id: int) -> None:
        """Reset the tracking state for an alert.

        Args:
            alert_id: ID of alert to reset
        """
        if alert_id in self._previous_states:
            del self._previous_states[alert_id]
