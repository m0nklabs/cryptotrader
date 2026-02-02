"""Signal reasoning engine - explains why to buy/sell.

Provides rule-based analysis and generates human-readable explanations
for trading decisions based on technical indicators.

Usage:
    from core.signals.reasoning import SignalReasoner, analyze_symbol

    # Quick analysis
    analysis = await analyze_symbol("BTCUSD", timeframe="4h")
    print(analysis.recommendation)
    print(analysis.reasoning)

    # Full reasoner
    reasoner = SignalReasoner()
    analysis = await reasoner.analyze("BTCUSD", "4h")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Sequence

from core.types import Candle

logger = logging.getLogger(__name__)


class Recommendation(str, Enum):
    """Trading recommendation."""

    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WAIT = "WAIT"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class KeyLevel:
    """Support/resistance level."""

    price: Decimal
    level_type: str  # "support" or "resistance"
    strength: int  # 0-100
    touches: int = 0
    notes: str = ""


@dataclass
class TechnicalAnalysis:
    """Complete technical analysis for a symbol."""

    symbol: str
    timeframe: str
    timestamp: datetime
    current_price: Decimal

    # Recommendation
    recommendation: Recommendation
    confidence: int  # 0-100

    # Reasoning
    reasoning: list[str] = field(default_factory=list)
    bullish_factors: list[str] = field(default_factory=list)
    bearish_factors: list[str] = field(default_factory=list)

    # Key levels
    support_levels: list[Decimal] = field(default_factory=list)
    resistance_levels: list[Decimal] = field(default_factory=list)

    # Trade suggestion
    suggested_entry: Optional[Decimal] = None
    suggested_stop: Optional[Decimal] = None
    suggested_target: Optional[Decimal] = None
    risk_reward_ratio: Optional[float] = None

    # Raw indicator values
    indicators: dict = field(default_factory=dict)


class SignalReasoner:
    """Analyzes market data and provides trading recommendations with reasoning."""

    # RSI thresholds
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    RSI_EXTREME_OVERSOLD = 20
    RSI_EXTREME_OVERBOUGHT = 80

    # Trend thresholds
    TREND_STRONG_THRESHOLD = 0.02  # 2% above/below EMA

    def __init__(self, db_url: str | None = None):
        """Initialize reasoner.

        Args:
            db_url: Database connection string (uses env var if not provided)
        """
        self.db_url = db_url

    async def analyze(
        self,
        symbol: str,
        timeframe: str = "4h",
        candles: Sequence[Candle] | None = None,
    ) -> TechnicalAnalysis:
        """Perform technical analysis on a symbol.

        Args:
            symbol: Trading pair (e.g., "BTCUSD")
            timeframe: Candle timeframe
            candles: Optional pre-fetched candles (fetches from DB if not provided)

        Returns:
            Complete technical analysis with recommendation
        """
        # Fetch candles if not provided
        if candles is None:
            candles = await self._fetch_candles(symbol, timeframe)

        if len(candles) < 200:
            logger.warning(f"Insufficient candles for {symbol} ({len(candles)} < 200)")
            return self._insufficient_data_response(symbol, timeframe, candles)

        # Calculate indicators
        indicators = self._calculate_indicators(candles)

        # Generate analysis
        current_price = candles[-1].close
        bullish, bearish = self._analyze_factors(indicators, current_price)

        # Calculate key levels
        support, resistance = self._find_key_levels(candles)

        # Generate recommendation
        recommendation, confidence = self._generate_recommendation(bullish, bearish, indicators)

        # Generate trade suggestion
        entry, stop, target, rr = self._suggest_trade(recommendation, current_price, support, resistance, indicators)

        # Compile reasoning
        reasoning = self._compile_reasoning(bullish, bearish, indicators)

        return TechnicalAnalysis(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now(timezone.utc),
            current_price=current_price,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            bullish_factors=bullish,
            bearish_factors=bearish,
            support_levels=support,
            resistance_levels=resistance,
            suggested_entry=entry,
            suggested_stop=stop,
            suggested_target=target,
            risk_reward_ratio=rr,
            indicators=indicators,
        )

    async def _fetch_candles(self, symbol: str, timeframe: str, limit: int = 300) -> list[Candle]:
        """Fetch candles from database."""
        import os
        import asyncpg

        db_url = self.db_url or os.environ.get("DATABASE_URL", "postgresql://localhost/cryptotrader")

        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch(
                """
                SELECT symbol, exchange, timeframe, open_time, close_time,
                       open, high, low, close, volume
                FROM candles
                WHERE symbol = $1 AND timeframe = $2
                ORDER BY open_time DESC
                LIMIT $3
                """,
                symbol,
                timeframe,
                limit,
            )

            candles = [
                Candle(
                    symbol=r["symbol"],
                    exchange=r["exchange"],
                    timeframe=r["timeframe"],
                    open_time=r["open_time"],
                    close_time=r["close_time"],
                    open=Decimal(str(r["open"])),
                    high=Decimal(str(r["high"])),
                    low=Decimal(str(r["low"])),
                    close=Decimal(str(r["close"])),
                    volume=Decimal(str(r["volume"])),
                )
                for r in reversed(rows)  # Oldest first
            ]
            return candles
        finally:
            await conn.close()

    def _calculate_indicators(self, candles: Sequence[Candle]) -> dict:
        """Calculate all technical indicators."""
        closes = [float(c.close) for c in candles]
        highs = [float(c.high) for c in candles]
        lows = [float(c.low) for c in candles]
        volumes = [float(c.volume) for c in candles]

        # RSI
        rsi = self._calc_rsi(closes, 14)

        # EMAs
        ema_20 = self._calc_ema(closes, 20)
        ema_50 = self._calc_ema(closes, 50)
        ema_200 = self._calc_ema(closes, 200)

        # MACD
        macd, signal, histogram = self._calc_macd(closes)

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = self._calc_bollinger(closes, 20, 2)

        # ATR
        atr = self._calc_atr(highs, lows, closes, 14)

        # Volume MA
        vol_ma = self._calc_sma(volumes, 20)

        current_price = closes[-1]

        return {
            "price": current_price,
            "rsi": rsi,
            "rsi_prev": self._calc_rsi(closes[:-1], 14) if len(closes) > 15 else rsi,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "macd": macd,
            "macd_signal": signal,
            "macd_histogram": histogram,
            "macd_histogram_prev": self._calc_macd(closes[:-1])[2] if len(closes) > 27 else histogram,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "atr": atr,
            "atr_percent": (atr / current_price) * 100 if current_price > 0 else 0,
            "volume": volumes[-1],
            "volume_ma": vol_ma,
            "volume_ratio": volumes[-1] / vol_ma if vol_ma > 0 else 1,
        }

    def _analyze_factors(self, indicators: dict, price: Decimal) -> tuple[list[str], list[str]]:
        """Analyze bullish and bearish factors."""
        bullish = []
        bearish = []
        price_f = float(price)

        # RSI analysis
        rsi = indicators["rsi"]
        if rsi <= self.RSI_EXTREME_OVERSOLD:
            bullish.append(f"RSI extremely oversold ({rsi:.0f}) - strong bounce potential")
        elif rsi <= self.RSI_OVERSOLD:
            bullish.append(f"RSI oversold ({rsi:.0f}) - potential bounce")
        elif rsi >= self.RSI_EXTREME_OVERBOUGHT:
            bearish.append(f"RSI extremely overbought ({rsi:.0f}) - strong pullback risk")
        elif rsi >= self.RSI_OVERBOUGHT:
            bearish.append(f"RSI overbought ({rsi:.0f}) - potential pullback")

        # RSI divergence
        rsi_prev = indicators["rsi_prev"]
        if rsi > rsi_prev and price_f < indicators.get("price_prev", price_f):
            bullish.append("Bullish RSI divergence detected")
        elif rsi < rsi_prev and price_f > indicators.get("price_prev", price_f):
            bearish.append("Bearish RSI divergence detected")

        # Trend analysis (EMA)
        ema_200 = indicators["ema_200"]
        ema_50 = indicators["ema_50"]
        # _ = indicators["ema_20"]  # Available but not used in reasoning

        if price_f > ema_200:
            pct_above = ((price_f - ema_200) / ema_200) * 100
            if pct_above > 5:
                bullish.append(f"Price {pct_above:.1f}% above EMA200 - strong uptrend")
            else:
                bullish.append("Price above EMA200 - bullish trend")
        else:
            pct_below = ((ema_200 - price_f) / ema_200) * 100
            if pct_below > 5:
                bearish.append(f"Price {pct_below:.1f}% below EMA200 - strong downtrend")
            else:
                bearish.append("Price below EMA200 - bearish trend")

        # Golden/Death cross
        if ema_50 > ema_200 and indicators.get("ema_50_prev", ema_50) <= indicators.get("ema_200_prev", ema_200):
            bullish.append("Golden cross (EMA50 > EMA200) - major bullish signal")
        elif ema_50 < ema_200 and indicators.get("ema_50_prev", ema_50) >= indicators.get("ema_200_prev", ema_200):
            bearish.append("Death cross (EMA50 < EMA200) - major bearish signal")
        elif ema_50 > ema_200:
            bullish.append("EMA50 above EMA200 - bullish structure")
        else:
            bearish.append("EMA50 below EMA200 - bearish structure")

        # MACD analysis
        macd = indicators["macd"]
        macd_signal = indicators["macd_signal"]
        histogram = indicators["macd_histogram"]
        histogram_prev = indicators["macd_histogram_prev"]

        if macd > macd_signal:
            if histogram > histogram_prev:
                bullish.append("MACD bullish with increasing momentum")
            else:
                bullish.append("MACD bullish but momentum fading")
        else:
            if histogram < histogram_prev:
                bearish.append("MACD bearish with increasing downward momentum")
            else:
                bearish.append("MACD bearish but downward momentum fading")

        # Bollinger Bands
        bb_upper = indicators["bb_upper"]
        bb_lower = indicators["bb_lower"]

        if price_f <= bb_lower:
            bullish.append("Price at lower Bollinger Band - potential bounce zone")
        elif price_f >= bb_upper:
            bearish.append("Price at upper Bollinger Band - potential resistance")

        # Volume analysis
        vol_ratio = indicators["volume_ratio"]
        if vol_ratio > 2:
            if price_f > indicators["ema_20"]:
                bullish.append(f"High volume ({vol_ratio:.1f}x avg) with bullish price action")
            else:
                bearish.append(f"High volume ({vol_ratio:.1f}x avg) with bearish price action")
        elif vol_ratio < 0.5:
            bearish.append("Low volume - weak conviction in current move")

        # Volatility
        atr_pct = indicators["atr_percent"]
        if atr_pct > 5:
            bearish.append(f"High volatility (ATR {atr_pct:.1f}%) - increased risk")

        return bullish, bearish

    def _find_key_levels(self, candles: Sequence[Candle], lookback: int = 50) -> tuple[list[Decimal], list[Decimal]]:
        """Find support and resistance levels from recent price action."""
        recent = candles[-lookback:]

        highs = [float(c.high) for c in recent]
        lows = [float(c.low) for c in recent]
        current = float(candles[-1].close)

        # Find swing highs (resistance)
        resistance = []
        for i in range(2, len(highs) - 2):
            if (
                highs[i] > highs[i - 1]
                and highs[i] > highs[i - 2]
                and highs[i] > highs[i + 1]
                and highs[i] > highs[i + 2]
            ):
                if highs[i] > current:  # Only levels above current price
                    resistance.append(Decimal(str(round(highs[i], 2))))

        # Find swing lows (support)
        support = []
        for i in range(2, len(lows) - 2):
            if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
                if lows[i] < current:  # Only levels below current price
                    support.append(Decimal(str(round(lows[i], 2))))

        # Sort and deduplicate (within 1% of each other)
        support = self._deduplicate_levels(sorted(support, reverse=True))[:3]
        resistance = self._deduplicate_levels(sorted(resistance))[:3]

        return support, resistance

    def _deduplicate_levels(self, levels: list[Decimal], threshold: float = 0.01) -> list[Decimal]:
        """Remove levels that are too close to each other."""
        if not levels:
            return []

        result = [levels[0]]
        for level in levels[1:]:
            if abs(float(level - result[-1]) / float(result[-1])) > threshold:
                result.append(level)
        return result

    def _generate_recommendation(
        self,
        bullish: list[str],
        bearish: list[str],
        indicators: dict,
    ) -> tuple[Recommendation, int]:
        """Generate trading recommendation from factors."""
        bull_score = len(bullish)
        bear_score = len(bearish)

        # Weight important factors more
        for factor in bullish:
            if "extremely oversold" in factor.lower():
                bull_score += 2
            elif "golden cross" in factor.lower():
                bull_score += 2
            elif "strong uptrend" in factor.lower():
                bull_score += 1
            elif "bullish divergence" in factor.lower():
                bull_score += 1

        for factor in bearish:
            if "extremely overbought" in factor.lower():
                bear_score += 2
            elif "death cross" in factor.lower():
                bear_score += 2
            elif "strong downtrend" in factor.lower():
                bear_score += 1
            elif "bearish divergence" in factor.lower():
                bear_score += 1

        # Calculate net score
        net = bull_score - bear_score
        total = bull_score + bear_score
        confidence = int((abs(net) / max(total, 1)) * 100)
        confidence = min(confidence, 95)  # Cap at 95%

        # Generate recommendation
        if net >= 5:
            return Recommendation.STRONG_BUY, confidence
        elif net >= 2:
            return Recommendation.BUY, confidence
        elif net <= -5:
            return Recommendation.STRONG_SELL, confidence
        elif net <= -2:
            return Recommendation.SELL, confidence
        else:
            return Recommendation.WAIT, confidence

    def _suggest_trade(
        self,
        recommendation: Recommendation,
        current_price: Decimal,
        support: list[Decimal],
        resistance: list[Decimal],
        indicators: dict,
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[float]]:
        """Suggest entry, stop, and target prices."""
        if recommendation == Recommendation.WAIT:
            return None, None, None, None

        price_f = float(current_price)
        atr = indicators["atr"]

        if recommendation in (Recommendation.BUY, Recommendation.STRONG_BUY):
            # Entry at current or slightly below
            entry = current_price

            # Stop below nearest support or 2x ATR
            if support:
                stop = support[0] - Decimal(str(atr * 0.5))
            else:
                stop = Decimal(str(price_f - atr * 2))

            # Target at nearest resistance or 3x risk
            risk = float(entry - stop)
            if resistance:
                target = resistance[0]
            else:
                target = Decimal(str(price_f + risk * 3))

        else:  # SELL
            entry = current_price

            # Stop above nearest resistance or 2x ATR
            if resistance:
                stop = resistance[0] + Decimal(str(atr * 0.5))
            else:
                stop = Decimal(str(price_f + atr * 2))

            # Target at nearest support or 3x risk
            risk = float(stop - entry)
            if support:
                target = support[0]
            else:
                target = Decimal(str(price_f - risk * 3))

        # Calculate risk/reward
        risk = abs(float(entry - stop))
        reward = abs(float(target - entry))
        rr = reward / risk if risk > 0 else 0

        return entry, stop, target, round(rr, 2)

    def _compile_reasoning(
        self,
        bullish: list[str],
        bearish: list[str],
        indicators: dict,
    ) -> list[str]:
        """Compile all factors into coherent reasoning."""
        reasoning = []

        # Start with trend
        price = indicators["price"]
        ema_200 = indicators["ema_200"]
        if price > ema_200:
            reasoning.append("Macro trend is BULLISH (price above EMA200)")
        else:
            reasoning.append("Macro trend is BEARISH (price below EMA200)")

        # Add momentum
        rsi = indicators["rsi"]
        if rsi < 30:
            reasoning.append(f"Momentum showing oversold conditions (RSI={rsi:.0f})")
        elif rsi > 70:
            reasoning.append(f"Momentum showing overbought conditions (RSI={rsi:.0f})")
        else:
            reasoning.append(f"Momentum is neutral (RSI={rsi:.0f})")

        # Add key factors
        reasoning.extend(bullish[:2])  # Top 2 bullish
        reasoning.extend(bearish[:2])  # Top 2 bearish

        return reasoning

    def _insufficient_data_response(self, symbol: str, timeframe: str, candles: Sequence[Candle]) -> TechnicalAnalysis:
        """Return analysis when insufficient data."""
        return TechnicalAnalysis(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now(timezone.utc),
            current_price=candles[-1].close if candles else Decimal("0"),
            recommendation=Recommendation.WAIT,
            confidence=0,
            reasoning=[f"Insufficient data ({len(candles)} candles, need 200+)"],
            bullish_factors=[],
            bearish_factors=[],
        )

    # =========================================================================
    # Technical indicator calculations
    # =========================================================================

    def _calc_rsi(self, prices: list[float], period: int = 14) -> float:
        """Calculate RSI."""
        if len(prices) < period + 1:
            return 50.0

        deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calc_ema(self, prices: list[float], period: int) -> float:
        """Calculate EMA."""
        if len(prices) < period:
            return prices[-1] if prices else 0

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # SMA for first value

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calc_sma(self, prices: list[float], period: int) -> float:
        """Calculate SMA."""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        return sum(prices[-period:]) / period

    def _calc_macd(
        self, prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[float, float, float]:
        """Calculate MACD, Signal, and Histogram."""
        if len(prices) < slow + signal:
            return 0, 0, 0

        ema_fast = self._calc_ema(prices, fast)
        ema_slow = self._calc_ema(prices, slow)
        macd_line = ema_fast - ema_slow

        # Calculate signal line (EMA of MACD)
        macd_values = []
        for i in range(slow, len(prices) + 1):
            ef = self._calc_ema(prices[:i], fast)
            es = self._calc_ema(prices[:i], slow)
            macd_values.append(ef - es)

        signal_line = self._calc_ema(macd_values, signal) if len(macd_values) >= signal else macd_line
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def _calc_bollinger(self, prices: list[float], period: int = 20, std_dev: float = 2) -> tuple[float, float, float]:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            return prices[-1], prices[-1], prices[-1]

        recent = prices[-period:]
        middle = sum(recent) / period
        variance = sum((p - middle) ** 2 for p in recent) / period
        std = variance**0.5

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return upper, middle, lower

    def _calc_atr(self, highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
        """Calculate ATR."""
        if len(highs) < period + 1:
            return 0

        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            true_ranges.append(tr)

        return sum(true_ranges[-period:]) / period


# Convenience function
async def analyze_symbol(
    symbol: str,
    timeframe: str = "4h",
    db_url: str | None = None,
) -> TechnicalAnalysis:
    """Quick analysis of a symbol.

    Args:
        symbol: Trading pair (e.g., "BTCUSD")
        timeframe: Candle timeframe
        db_url: Optional database URL

    Returns:
        Technical analysis with recommendation
    """
    reasoner = SignalReasoner(db_url=db_url)
    return await reasoner.analyze(symbol, timeframe)
