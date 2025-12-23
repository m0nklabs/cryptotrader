"""Signal detection engine for trading opportunities.

Detects simple patterns:
- RSI overbought/oversold
- Golden/death cross (MA crossover)
- Volume spike

Usage:
    from core.signals.detector import detect_signals
    from core.types import Candle

    signals = detect_signals(candles=candles, symbol="BTCUSD", timeframe="1h")
"""

from __future__ import annotations

from typing import Sequence

from core.indicators.rsi import compute_rsi, generate_rsi_signal
from core.types import Candle, IndicatorSignal, Opportunity, SignalSide


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
    
    # Determine overall side (majority vote, excluding CONFIRM)
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
        "RSI": 0.35,
        "MA_CROSS": 0.40,
        "VOLUME_SPIKE": 0.25,
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
    
    return Opportunity(
        symbol=symbol,
        timeframe=timeframe,
        score=score,
        side=side,
        signals=tuple(signals),
    )
