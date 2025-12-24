"""Signal detection engine for trading opportunities.

Detects patterns:
- RSI overbought/oversold
- MACD crossover
- Stochastic overbought/oversold
- Bollinger Bands breakout
- ATR volatility
- Golden/death cross (MA crossover)
- Volume spike

Usage:
    from core.signals.detector import detect_signals
    from core.types import Candle

    signals = detect_signals(candles=candles, symbol="BTCUSD", timeframe="1h")
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from core.indicators.atr import generate_atr_signal
from core.indicators.bollinger import generate_bollinger_signal
from core.indicators.macd import generate_macd_signal
from core.indicators.rsi import generate_rsi_signal
from core.indicators.stochastic import generate_stochastic_signal
from core.types import Candle, IndicatorSignal, Opportunity, SignalSide

# Optional dependencies (for alerts)
try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    from plyer import notification
except ImportError:
    notification = None  # type: ignore

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages alerts for detected trading signals.
    
    Supports:
    - Desktop notifications (via plyer or notify-send)
    - File logging to logs/signals.log
    - Webhook notifications (Discord/Slack)
    
    Configuration via environment variables:
    - SIGNAL_ALERTS_ENABLED: Enable/disable alerts (default: false)
    - SIGNAL_WEBHOOK_URL: Optional webhook URL for POST notifications
    """
    
    def __init__(self, *, enabled: bool | None = None, webhook_url: str | None = None, log_dir: Path | None = None):
        """Initialize AlertManager.
        
        Args:
            enabled: Enable alerts (reads SIGNAL_ALERTS_ENABLED env var if None)
            webhook_url: Webhook URL (reads SIGNAL_WEBHOOK_URL env var if None)
            log_dir: Directory for signal logs (defaults to ./logs)
        """
        # Read from env vars if not explicitly provided
        if enabled is None:
            enabled = os.environ.get("SIGNAL_ALERTS_ENABLED", "false").lower() in ("true", "1", "yes")
        if webhook_url is None:
            webhook_url = os.environ.get("SIGNAL_WEBHOOK_URL", "")
        
        self.enabled = enabled
        self.webhook_url = webhook_url.strip() if webhook_url else ""
        self.log_dir = log_dir or Path(__file__).resolve().parents[2] / "logs"
        self.log_file = self.log_dir / "signals.log"
        
        # Ensure log directory exists
        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def alert(self, opportunity: Opportunity, exchange: str = "bitfinex") -> None:
        """Send alert for detected trading opportunity.
        
        Args:
            opportunity: Detected trading opportunity
            exchange: Exchange name (default: bitfinex)
        """
        if not self.enabled:
            return
        
        try:
            # Log to file (always)
            self._log_to_file(opportunity, exchange)
            
            # Desktop notification
            self._send_desktop_notification(opportunity, exchange)
            
            # Webhook notification (if configured)
            if self.webhook_url:
                self._send_webhook(opportunity, exchange)
        except Exception as exc:
            logger.warning(f"Failed to send alert for {opportunity.symbol}: {exc}")
    
    def _log_to_file(self, opportunity: Opportunity, exchange: str) -> None:
        """Append signal to log file with structured format."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Build signal details (avoid logging sensitive data)
        signal_details = [
            f"{sig.code}:{sig.side}:{sig.strength}" for sig in opportunity.signals
        ]
        
        log_entry = {
            "timestamp": timestamp,
            "exchange": exchange,
            "symbol": opportunity.symbol,
            "timeframe": opportunity.timeframe,
            "side": opportunity.side,
            "score": opportunity.score,
            "signals": signal_details,
        }
        
        # Append as JSON line
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    
    def _send_desktop_notification(self, opportunity: Opportunity, exchange: str) -> None:
        """Send desktop notification using plyer or notify-send fallback."""
        title = f"🔔 Signal: {opportunity.symbol}"
        message = (
            f"{opportunity.side} signal detected\n"
            f"Score: {opportunity.score}/100\n"
            f"Timeframe: {opportunity.timeframe}\n"
            f"Signals: {len(opportunity.signals)}"
        )
        
        # Try plyer first
        if notification is not None:
            try:
                notification.notify(
                    title=title,
                    message=message,
                    app_name="CryptoTrader",
                    timeout=10,
                )
                return
            except Exception:
                pass
        
        # Fallback to notify-send (Linux)
        try:
            subprocess.run(
                ["notify-send", title, message],
                check=False,
                timeout=5,
                capture_output=True,
            )
        except Exception:
            # Silent fail if no notification system available
            pass
    
    def _send_webhook(self, opportunity: Opportunity, exchange: str) -> None:
        """Send webhook notification (Discord/Slack compatible)."""
        if requests is None:
            logger.warning("requests library not available, skipping webhook")
            return
        
        # Build signal summary
        signal_summary = ", ".join([
            f"{sig.code} ({sig.side}, {sig.strength}%)" for sig in opportunity.signals
        ])
        
        # Discord/Slack webhook payload
        payload = {
            "content": (
                f"🔔 **{opportunity.side} Signal Detected**\n"
                f"**Symbol:** {opportunity.symbol} ({exchange})\n"
                f"**Timeframe:** {opportunity.timeframe}\n"
                f"**Score:** {opportunity.score}/100\n"
                f"**Signals:** {signal_summary}"
            )
        }
        
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"Webhook notification failed: {exc}")


# Global alert manager instance (lazy initialization)
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get or create global AlertManager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


def detect_rsi_signal(candles: Sequence[Candle], *, period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> IndicatorSignal | None:
    """Detect RSI overbought/oversold signal.
    
    Args:
        candles: Sequence of OHLCV candles
        period: RSI period (default: 14)
        oversold: Oversold threshold (default: 30)
        overbought: Overbought threshold (default: 70)
        
    Returns:
        IndicatorSignal if oversold or overbought, None if neutral
    """
    if len(candles) < period + 1:
        return None
    
    try:
        signal = generate_rsi_signal(candles, period=period, oversold=oversold, overbought=overbought)
        # Only return signals for BUY/SELL (not HOLD)
        if signal.side in ("BUY", "SELL"):
            return signal
    except Exception:
        return None
    
    return None


def detect_ma_crossover(candles: Sequence[Candle], *, fast_period: int = 50, slow_period: int = 200) -> IndicatorSignal | None:
    """Detect Golden/Death cross (MA crossover).
    
    Golden cross: fast MA crosses above slow MA (bullish)
    Death cross: fast MA crosses below slow MA (bearish)
    
    Args:
        candles: Sequence of OHLCV candles
        fast_period: Fast MA period (default: 50)
        slow_period: Slow MA period (default: 200)
        
    Returns:
        IndicatorSignal if crossover detected, None otherwise
    """
    if len(candles) < slow_period + 2:
        return None
    
    try:
        # Calculate MAs for current and previous candle
        closes = [float(c.close) for c in candles]
        
        # Current MAs
        fast_ma = sum(closes[-fast_period:]) / fast_period
        slow_ma = sum(closes[-slow_period:]) / slow_period
        
        # Previous MAs
        prev_fast_ma = sum(closes[-fast_period-1:-1]) / fast_period
        prev_slow_ma = sum(closes[-slow_period-1:-1]) / slow_period
        
        # Detect crossover
        if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
            # Golden cross
            return IndicatorSignal(
                code="MA_CROSS",
                side="BUY",
                strength=80,
                value=f"MA({fast_period})={fast_ma:.2f} > MA({slow_period})={slow_ma:.2f}",
                reason=f"Golden cross: MA({fast_period}) crossed above MA({slow_period})",
            )
        elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
            # Death cross
            return IndicatorSignal(
                code="MA_CROSS",
                side="SELL",
                strength=80,
                value=f"MA({fast_period})={fast_ma:.2f} < MA({slow_period})={slow_ma:.2f}",
                reason=f"Death cross: MA({fast_period}) crossed below MA({slow_period})",
            )
    except Exception:
        return None
    
    return None


def detect_volume_spike(candles: Sequence[Candle], *, period: int = 20, threshold: float = 2.0) -> IndicatorSignal | None:
    """Detect volume spike.
    
    Args:
        candles: Sequence of OHLCV candles
        period: Lookback period for average volume (default: 20)
        threshold: Spike threshold (current volume / avg volume, default: 2.0)
        
    Returns:
        IndicatorSignal if volume spike detected, None otherwise
    """
    if len(candles) < period + 1:
        return None
    
    try:
        volumes = [float(c.volume) for c in candles]
        current_volume = volumes[-1]
        avg_volume = sum(volumes[-period-1:-1]) / period
        
        if avg_volume <= 0:
            return None
        
        ratio = current_volume / avg_volume
        
        if ratio >= threshold:
            # Volume spike confirms current trend
            strength = min(100, int((ratio - threshold) * 50 + 50))
            return IndicatorSignal(
                code="VOLUME_SPIKE",
                side="CONFIRM",
                strength=strength,
                value=f"{ratio:.2f}x avg",
                reason=f"Volume spike: {ratio:.2f}x average (threshold: {threshold}x)",
            )
    except Exception:
        return None
    
    return None


def detect_macd_signal(
    candles: Sequence[Candle], *, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> IndicatorSignal | None:
    """Detect MACD crossover signal.

    Args:
        candles: Sequence of OHLCV candles
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal_period: Signal line period (default: 9)

    Returns:
        IndicatorSignal if crossover detected, None if neutral
    """
    if len(candles) < slow + signal_period + 1:
        return None

    try:
        signal = generate_macd_signal(candles, fast=fast, slow=slow, signal_period=signal_period)
        # Only return signals for BUY/SELL (not HOLD)
        if signal.side in ("BUY", "SELL"):
            return signal
    except Exception:
        return None

    return None


def detect_stochastic_signal(
    candles: Sequence[Candle], *, k_period: int = 14, d_period: int = 3, oversold: float = 20.0, overbought: float = 80.0
) -> IndicatorSignal | None:
    """Detect Stochastic overbought/oversold signal.

    Args:
        candles: Sequence of OHLCV candles
        k_period: %K period (default: 14)
        d_period: %D smoothing period (default: 3)
        oversold: Oversold threshold (default: 20)
        overbought: Overbought threshold (default: 80)

    Returns:
        IndicatorSignal if oversold or overbought, None if neutral
    """
    if len(candles) < k_period + d_period:
        return None

    try:
        signal = generate_stochastic_signal(
            candles, k_period=k_period, d_period=d_period, oversold=oversold, overbought=overbought
        )
        # Only return signals for BUY/SELL (not HOLD)
        if signal.side in ("BUY", "SELL"):
            return signal
    except Exception:
        return None

    return None


def detect_bollinger_signal(candles: Sequence[Candle], *, period: int = 20, std_dev: float = 2.0) -> IndicatorSignal | None:
    """Detect Bollinger Bands breakout signal.

    Args:
        candles: Sequence of OHLCV candles
        period: SMA period (default: 20)
        std_dev: Standard deviations (default: 2.0)

    Returns:
        IndicatorSignal if price at/beyond bands, None if within bands
    """
    if len(candles) < period:
        return None

    try:
        signal = generate_bollinger_signal(candles, period=period, std_dev=std_dev)
        # Only return signals for BUY/SELL (not HOLD)
        if signal.side in ("BUY", "SELL"):
            return signal
    except Exception:
        return None

    return None


def detect_atr_signal(
    candles: Sequence[Candle],
    *,
    period: int = 14,
    high_volatility_threshold: float = 1.5,
    low_volatility_threshold: float = 0.5,
) -> IndicatorSignal | None:
    """Detect ATR volatility signal.

    Args:
        candles: Sequence of OHLCV candles
        period: ATR period (default: 14)
        high_volatility_threshold: High volatility threshold (default: 1.5)
        low_volatility_threshold: Low volatility threshold (default: 0.5)

    Returns:
        IndicatorSignal if extreme volatility detected, None if normal
    """
    if len(candles) < period + 1:
        return None

    try:
        signal = generate_atr_signal(
            candles,
            period=period,
            high_volatility_threshold=high_volatility_threshold,
            low_volatility_threshold=low_volatility_threshold,
        )
        # ATR signals are informational (volatility), return if strength > 0
        if signal.strength > 0:
            return signal
    except Exception:
        return None

    return None


def detect_signals(*, candles: Sequence[Candle], symbol: str, timeframe: str, exchange: str = "bitfinex") -> Opportunity | None:
    """Detect all signals for a symbol/timeframe and create an Opportunity.
    
    Args:
        candles: Sequence of OHLCV candles
        symbol: Trading symbol (e.g., "BTCUSD")
        timeframe: Timeframe (e.g., "1h")
        exchange: Exchange name (default: "bitfinex")
        
    Returns:
        Opportunity with detected signals and score, or None if no signals
    """
    if len(candles) < 15:
        return None
    
    signals: list[IndicatorSignal] = []
    
    # Detect RSI
    rsi_signal = detect_rsi_signal(candles)
    if rsi_signal:
        signals.append(rsi_signal)
    
    # Detect MACD
    macd_signal = detect_macd_signal(candles)
    if macd_signal:
        signals.append(macd_signal)
    
    # Detect Stochastic
    stoch_signal = detect_stochastic_signal(candles)
    if stoch_signal:
        signals.append(stoch_signal)
    
    # Detect Bollinger Bands
    bb_signal = detect_bollinger_signal(candles)
    if bb_signal:
        signals.append(bb_signal)
    
    # Detect ATR (volatility)
    atr_signal = detect_atr_signal(candles)
    if atr_signal:
        signals.append(atr_signal)
    
    # Detect MA crossover
    ma_signal = detect_ma_crossover(candles)
    if ma_signal:
        signals.append(ma_signal)
    
    # Detect volume spike
    vol_signal = detect_volume_spike(candles)
    if vol_signal:
        signals.append(vol_signal)
    
    if not signals:
        return None
    
    # Determine overall side (majority vote, excluding CONFIRM and HOLD)
    buy_signals = [s for s in signals if s.side == "BUY"]
    sell_signals = [s for s in signals if s.side == "SELL"]
    
    if len(buy_signals) > len(sell_signals):
        side: SignalSide = "BUY"
    elif len(sell_signals) > len(buy_signals):
        side = "SELL"
    else:
        side = "HOLD"
    
    # Calculate weighted score
    weights = {
        "RSI": 0.20,
        "MACD": 0.25,
        "STOCHASTIC": 0.15,
        "BOLLINGER": 0.15,
        "ATR": 0.05,
        "MA_CROSS": 0.15,
        "VOLUME_SPIKE": 0.05,
    }
    
    total_weight = 0.0
    weighted_score = 0.0
    
    for sig in signals:
        if sig.side in ("BUY", "SELL"):
            weight = weights.get(sig.code, 0.15)
            weighted_score += weight * sig.strength
            total_weight += weight
    
    if total_weight > 0:
        score = int(round(weighted_score / total_weight))
    else:
        score = 0
    
    opportunity = Opportunity(
        symbol=symbol,
        timeframe=timeframe,
        score=score,
        side=side,
        signals=tuple(signals),
    )
    
    # Send alert if enabled
    try:
        alert_manager = get_alert_manager()
        alert_manager.alert(opportunity, exchange=exchange)
    except Exception as exc:
        logger.warning(f"Failed to send alert: {exc}")
    
    return opportunity
