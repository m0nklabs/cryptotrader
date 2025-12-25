"""
Technical Indicators Calculator
Supports: RSI, MACD, Stochastic, Moving Averages, Bollinger Bands, Volume indicators

Usage (OHLCV candles):
    candles = [
        {'open': 100, 'high': 105, 'low': 98, 'close': 102, 'volume': 1000},
        {'open': 102, 'high': 108, 'low': 101, 'close': 106, 'volume': 1200},
        ...
    ]

    ind = TechnicalIndicators(candles)
    rsi = ind.rsi()
    k, d = ind.stochastic()  # Now uses true High/Low!

    # Backward compatible with price lists
    prices = [100, 101, 99, 102, 103, ...]
    ind = TechnicalIndicators(prices)  # Auto-converts to OHLCV format

    # Generate trading signals
    signal_gen = SignalGenerator(ind, current_price=103.50)
    analysis = signal_gen.analyze_all()
    print(f"Signal: {analysis['signal']} ({analysis['strength']}%)")
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Calculate technical indicators from OHLCV candle data"""

    def __init__(self, data: Union[List[Dict], List[float]], volumes: Optional[List[float]] = None):
        """
        Initialize with OHLCV candles or price list (backward compatible)

        Args:
            data: Either list of OHLCV dicts or list of close prices
            volumes: Optional volumes (only used if data is price list)

        OHLCV dict format:
            {'open': 100, 'high': 105, 'low': 98, 'close': 102, 'volume': 1000}
        """
        if not data:
            raise ValueError("Need at least 1 data point")

        # Check if data is OHLCV candles or price list
        if isinstance(data[0], dict):
            # OHLCV candles
            self.df = pd.DataFrame(data)
            required_cols = ["open", "high", "low", "close"]
            if not all(col in self.df.columns for col in required_cols):
                raise ValueError(f"OHLCV data must contain: {required_cols}")

            # Ensure volume column exists
            if "volume" not in self.df.columns:
                self.df["volume"] = 0

            logger.debug(f"🐛 Initialized with {len(data)} OHLCV candles")
        else:
            # Backward compatible: price list
            if len(data) < 2:
                raise ValueError("Need at least 2 price points")

            # Convert to OHLCV format (close = open = high = low)
            self.df = pd.DataFrame(
                {
                    "open": data,
                    "high": data,  # Estimate: same as close
                    "low": data,  # Estimate: same as close
                    "close": data,
                    "volume": volumes if volumes else [0] * len(data),
                }
            )
            logger.debug(f"🐛 Initialized with {len(data)} price points (converted to OHLCV)")

    # ========== MOMENTUM INDICATORS ==========

    def rsi(self, period: int = 14) -> float:
        """
        Relative Strength Index (0-100)

        Interpretation:
            < 30: Oversold (BUY signal)
            > 70: Overbought (SELL signal)
            30-70: Neutral

        Args:
            period: Lookback period (default 14)

        Returns:
            RSI value (0-100)
        """
        if len(self.df) < period + 1:
            logger.warning(f"⚠️ Not enough data for RSI({period}): need {period+1}, have {len(self.df)}")
            return 50.0  # Return neutral

        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period, min_periods=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        result = rsi.iloc[-1]
        logger.debug(f"📊 RSI({period}): {result:.2f}")
        return result

    def stochastic(self, k_period: int = 14, d_period: int = 3) -> Tuple[float, float]:
        """
        Stochastic Oscillator (0-100) - NOW USES TRUE HIGH/LOW!

        Interpretation:
            < 20: Oversold (BUY)
            > 80: Overbought (SELL)

        Args:
            k_period: %K period (default 14)
            d_period: %D smoothing period (default 3)

        Returns:
            Tuple of (%K, %D) values
        """
        if len(self.df) < k_period:
            logger.warning(f"⚠️ Not enough data for Stochastic({k_period})")
            return 50.0, 50.0

        # TRUE HIGH/LOW from OHLCV data!
        low_min = self.df["low"].rolling(window=k_period).min()
        high_max = self.df["high"].rolling(window=k_period).max()

        k = 100 * (self.df["close"] - low_min) / (high_max - low_min)
        d = k.rolling(window=d_period).mean()

        k_val = k.iloc[-1]
        d_val = d.iloc[-1]
        logger.debug(f"📊 Stochastic: %K={k_val:.2f}, %D={d_val:.2f}")
        return k_val, d_val

    def cci(self, period: int = 20) -> float:
        """
        Commodity Channel Index

        Interpretation:
            < -100: Oversold (BUY)
            > +100: Overbought (SELL)

        Args:
            period: Lookback period (default 20)

        Returns:
            CCI value
        """
        if len(self.df) < period:
            logger.warning(f"⚠️ Not enough data for CCI({period})")
            return 0.0

        tp = self.df["close"]  # Typical price (simplified: close only)
        sma = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())

        cci = (tp - sma) / (0.015 * mad)
        result = cci.iloc[-1]
        logger.debug(f"📊 CCI({period}): {result:.2f}")
        return result

    def williams_r(self, period: int = 14) -> float:
        """
        Williams %R (-100 to 0)

        Interpretation:
            < -80: Oversold (BUY)
            > -20: Overbought (SELL)

        Args:
            period: Lookback period (default 14)

        Returns:
            Williams %R value (-100 to 0)
        """
        if len(self.df) < period:
            logger.warning(f"⚠️ Not enough data for Williams %R({period})")
            return -50.0

        high_max = self.df["close"].rolling(window=period).max()
        low_min = self.df["close"].rolling(window=period).min()

        wr = -100 * (high_max - self.df["close"]) / (high_max - low_min)
        result = wr.iloc[-1]
        logger.debug(f"📊 Williams %R({period}): {result:.2f}")
        return result

    # ========== TREND INDICATORS ==========

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """
        MACD (Moving Average Convergence Divergence)

        Interpretation:
            Bullish: MACD crosses above signal (BUY)
            Bearish: MACD crosses below signal (SELL)
            Histogram > 0: Bullish momentum
            Histogram < 0: Bearish momentum

        Args:
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line period (default 9)

        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        if len(self.df) < slow:
            logger.warning(f"⚠️ Not enough data for MACD({fast},{slow},{signal})")
            return 0.0, 0.0, 0.0

        ema_fast = self.df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        macd_val = macd_line.iloc[-1]
        signal_val = signal_line.iloc[-1]
        hist_val = histogram.iloc[-1]
        logger.debug(f"📊 MACD: {macd_val:.2f}, Signal: {signal_val:.2f}, Hist: {hist_val:.2f}")
        return macd_val, signal_val, hist_val

    def moving_averages(self, periods: List[int] = [20, 50, 200]) -> Dict[int, float]:
        """
        Simple Moving Averages

        Interpretation:
            Price > MA: Bullish
            Price < MA: Bearish
            Golden Cross: MA(50) > MA(200) (BULLISH)
            Death Cross: MA(50) < MA(200) (BEARISH)

        Args:
            periods: List of MA periods (default [20, 50, 200])

        Returns:
            Dict of {period: ma_value}
        """
        mas = {}
        for period in periods:
            if len(self.df) < period:
                logger.warning(f"⚠️ Not enough data for MA({period})")
                mas[period] = self.df["close"].iloc[-1]
            else:
                mas[period] = self.df["close"].rolling(window=period).mean().iloc[-1]
                logger.debug(f"📊 MA({period}): ${mas[period]:.2f}")
        return mas

    def ema(self, periods: List[int] = [12, 26]) -> Dict[int, float]:
        """
        Exponential Moving Averages

        Interpretation:
            Similar to SMA but more responsive to recent prices

        Args:
            periods: List of EMA periods (default [12, 26])

        Returns:
            Dict of {period: ema_value}
        """
        emas = {}
        for period in periods:
            if len(self.df) < period:
                logger.warning(f"⚠️ Not enough data for EMA({period})")
                emas[period] = self.df["close"].iloc[-1]
            else:
                emas[period] = self.df["close"].ewm(span=period, adjust=False).mean().iloc[-1]
                logger.debug(f"📊 EMA({period}): ${emas[period]:.2f}")
        return emas

    # ========== VOLATILITY INDICATORS ==========

    def bollinger_bands(self, period: int = 20, std_dev: int = 2) -> Tuple[float, float, float]:
        """
        Bollinger Bands (upper, middle, lower)

        Interpretation:
            Price near lower band: Oversold (BUY)
            Price near upper band: Overbought (SELL)
            Bands squeeze: Low volatility (breakout coming)
            Bands expand: High volatility

        Args:
            period: MA period (default 20)
            std_dev: Standard deviations (default 2)

        Returns:
            Tuple of (upper, middle, lower)
        """
        if len(self.df) < period:
            logger.warning(f"⚠️ Not enough data for Bollinger Bands({period})")
            current = self.df["close"].iloc[-1]
            return current, current, current

        sma = self.df["close"].rolling(window=period).mean()
        std = self.df["close"].rolling(window=period).std()

        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)

        upper_val = upper.iloc[-1]
        middle_val = sma.iloc[-1]
        lower_val = lower.iloc[-1]
        logger.debug(f"📊 Bollinger: Upper={upper_val:.2f}, Middle={middle_val:.2f}, Lower={lower_val:.2f}")
        return upper_val, middle_val, lower_val

    def atr(self, period: int = 14) -> float:
        """
        Average True Range (volatility measure)

        Interpretation:
            Higher ATR = Higher volatility
            Lower ATR = Lower volatility

        Args:
            period: Lookback period (default 14)

        Returns:
            ATR value
        """
        if len(self.df) < period + 1:
            logger.warning(f"⚠️ Not enough data for ATR({period})")
            return 0.0

        # Simplified ATR using close-to-close changes
        tr = self.df["close"].diff().abs()
        atr = tr.rolling(window=period).mean()

        result = atr.iloc[-1]
        logger.debug(f"📊 ATR({period}): {result:.2f}")
        return result

    # ========== VOLUME INDICATORS ==========

    def obv(self) -> float:
        """
        On-Balance Volume

        Interpretation:
            Rising OBV = Bullish (BUY)
            Falling OBV = Bearish (SELL)
            OBV divergence from price = Trend reversal warning

        Returns:
            Current OBV value
        """
        if len(self.df) < 2:
            return 0.0

        obv = (np.sign(self.df["close"].diff()) * self.df["volume"]).fillna(0).cumsum()
        result = obv.iloc[-1]
        logger.debug(f"📊 OBV: {result:.0f}")
        return result

    def volume_ratio(self, period: int = 20) -> float:
        """
        Volume vs Average Volume

        Interpretation:
            > 1.5: High volume (confirms trend)
            < 0.5: Low volume (weak trend)
            1.0: Normal volume

        Args:
            period: Lookback period for average (default 20)

        Returns:
            Volume ratio (current / average)
        """
        if len(self.df) < period:
            logger.warning(f"⚠️ Not enough data for Volume Ratio({period})")
            return 1.0

        avg_volume = self.df["volume"].rolling(window=period).mean()
        current_volume = self.df["volume"].iloc[-1]

        avg_val = avg_volume.iloc[-1]
        if avg_val == 0:
            return 1.0

        ratio = current_volume / avg_val
        logger.debug(f"📊 Volume Ratio: {ratio:.2f}x (current: {current_volume:.0f}, avg: {avg_val:.0f})")
        return ratio


class SignalGenerator:
    """Generate trading signals from technical indicators"""

    def __init__(self, indicators: TechnicalIndicators, current_price: float, indicator_config=None):
        """
        Initialize signal generator

        Args:
            indicators: TechnicalIndicators instance
            current_price: Current market price
            indicator_config: IndicatorConfig instance (optional, uses default if None)
        """
        self.ind = indicators
        self.price = current_price

        # Load indicator config (weights from database)
        if indicator_config is None:
            try:
                from .indicator_config import get_indicator_config

                self.config = get_indicator_config()
            except ImportError:
                logger.warning("⚠️  indicator_config not available, using hardcoded weights")
                self.config = None
        else:
            self.config = indicator_config

        logger.debug(f"🎯 Signal Generator initialized for price ${current_price:.2f}")
        if self.config:
            logger.debug(f"📊 Using database weights (total: {self.config.get_total_weight():.2f})")

    def _get_weight(self, indicator_code: str, default: float = 0.15) -> float:
        """Get weight for indicator from config or use default"""
        if self.config:
            return self.config.get_weight(indicator_code)
        return default

    def analyze_all(self) -> Dict:
        """
        Analyze all indicators and generate overall signal

        Returns:
            {
                'signal': 'BUY'|'SELL'|'HOLD',
                'strength': 0-100,
                'confidence': 0-100,
                'indicators': [...details...],
                'reasoning': [...explanations...]
            }
        """
        logger.debug("🔍 Starting full indicator analysis")
        signals = []

        # RSI
        try:
            rsi = self.ind.rsi()
            signals.append(self._analyze_rsi(rsi))
        except Exception as e:
            logger.error(f"❌ RSI analysis failed: {e}")

        # MACD
        try:
            macd_line, signal_line, histogram = self.ind.macd()
            signals.append(self._analyze_macd(macd_line, signal_line, histogram))
        except Exception as e:
            logger.error(f"❌ MACD analysis failed: {e}")

        # Stochastic
        try:
            k, d = self.ind.stochastic()
            signals.append(self._analyze_stochastic(k, d))
        except Exception as e:
            logger.error(f"❌ Stochastic analysis failed: {e}")

        # Moving Averages
        try:
            mas = self.ind.moving_averages()
            signals.append(self._analyze_ma(mas))
        except Exception as e:
            logger.error(f"❌ MA analysis failed: {e}")

        # Bollinger Bands
        try:
            upper, middle, lower = self.ind.bollinger_bands()
            signals.append(self._analyze_bollinger(upper, middle, lower))
        except Exception as e:
            logger.error(f"❌ Bollinger analysis failed: {e}")

        # Volume
        try:
            vol_ratio = self.ind.volume_ratio()
            signals.append(self._analyze_volume(vol_ratio))
        except Exception as e:
            logger.error(f"❌ Volume analysis failed: {e}")

        # Peak HiLo (multi-timeframe trend)
        try:
            if hasattr(self.ind, "peak_hilo") and self.ind.peak_hilo:
                direction = self.ind.peak_hilo.get("direction", "NONE")
                alignment = self.ind.peak_hilo.get("alignment", 0)
                signals.append(self._analyze_peak_hilo(direction, alignment))
        except Exception as e:
            logger.error(f"❌ Peak HiLo analysis failed: {e}")

        # Aggregate signals
        overall = self._aggregate_signals(signals)

        logger.debug(
            f"✅ Analysis complete: {overall['signal']} ({overall['strength']}% strength, {overall['confidence']}% confidence)"
        )

        return {
            "signal": overall["signal"],
            "strength": overall["strength"],
            "confidence": overall["confidence"],
            "indicators": signals,
            "reasoning": self._generate_reasoning(signals),
        }

    def _analyze_rsi(self, rsi: float) -> Dict:
        """Analyze RSI indicator"""
        weight = self.config.get_weight("RSI") if self.config else 0.15

        if rsi < 30:
            return {
                "name": "RSI",
                "value": round(rsi, 2),
                "signal": "BUY",
                "strength": min(100, int((30 - rsi) * 3)),  # Stronger when more oversold
                "weight": weight,
                "reason": "Oversold condition",
            }
        elif rsi > 70:
            return {
                "name": "RSI",
                "value": round(rsi, 2),
                "signal": "SELL",
                "strength": min(100, int((rsi - 70) * 3)),
                "weight": weight,
                "reason": "Overbought condition",
            }
        else:
            return {
                "name": "RSI",
                "value": round(rsi, 2),
                "signal": "HOLD",
                "strength": 0,
                "weight": self._get_weight("RSI", 0.15),
                "reason": "Neutral territory",
            }

    def _analyze_macd(self, macd_line: float, signal_line: float, histogram: float) -> Dict:
        """Analyze MACD indicator"""
        weight = self._get_weight("MACD", 0.20)

        if histogram > 0 and macd_line > signal_line:
            return {
                "name": "MACD",
                "value": round(histogram, 4),
                "signal": "BUY",
                "strength": min(100, int(abs(histogram) * 50)),
                "weight": weight,
                "reason": "Bullish crossover",
            }
        elif histogram < 0 and macd_line < signal_line:
            return {
                "name": "MACD",
                "value": round(histogram, 4),
                "signal": "SELL",
                "strength": min(100, int(abs(histogram) * 50)),
                "weight": weight,
                "reason": "Bearish crossover",
            }
        else:
            return {
                "name": "MACD",
                "value": round(histogram, 4),
                "signal": "HOLD",
                "strength": 0,
                "weight": weight,
                "reason": "No clear crossover",
            }

    def _analyze_stochastic(self, k: float, d: float) -> Dict:
        """Analyze Stochastic oscillator"""
        weight = self._get_weight("STOCHASTIC", 0.15)

        if k < 20:
            return {
                "name": "Stochastic",
                "value": round(k, 2),
                "signal": "BUY",
                "strength": min(100, int((20 - k) * 4)),
                "weight": weight,
                "reason": "Oversold condition",
            }
        elif k > 80:
            return {
                "name": "Stochastic",
                "value": round(k, 2),
                "signal": "SELL",
                "strength": min(100, int((k - 80) * 4)),
                "weight": weight,
                "reason": "Overbought condition",
            }
        else:
            return {
                "name": "Stochastic",
                "value": round(k, 2),
                "signal": "HOLD",
                "strength": 0,
                "weight": weight,
                "reason": "Neutral zone",
            }

    def _analyze_ma(self, mas: Dict[int, float]) -> Dict:
        """Analyze Moving Averages"""
        weight = self._get_weight("MA_CROSS", 0.15)

        ma_20 = mas.get(20, self.price)
        ma_50 = mas.get(50, self.price)
        ma_200 = mas.get(200, self.price)

        # Golden cross: MA(50) > MA(200)
        # Death cross: MA(50) < MA(200)

        if self.price > ma_20 and ma_50 > ma_200:
            return {
                "name": "Moving Averages",
                "value": f"${self.price:.2f} > MA(20)",
                "signal": "BUY",
                "strength": 65,
                "weight": weight,
                "reason": "Price above MA(20), golden cross present",
            }
        elif self.price < ma_20 and ma_50 < ma_200:
            return {
                "name": "Moving Averages",
                "value": f"${self.price:.2f} < MA(20)",
                "signal": "SELL",
                "strength": 65,
                "weight": weight,
                "reason": "Price below MA(20), death cross present",
            }
        else:
            return {
                "name": "Moving Averages",
                "value": f"${self.price:.2f}",
                "signal": "HOLD",
                "strength": 0,
                "weight": weight,
                "reason": "Mixed signals from MAs",
            }

    def _analyze_bollinger(self, upper: float, middle: float, lower: float) -> Dict:
        """Analyze Bollinger Bands"""
        weight = self._get_weight("BOLLINGER", 0.15)

        if self.price <= lower:
            return {
                "name": "Bollinger Bands",
                "value": f"${self.price:.2f} at lower band",
                "signal": "BUY",
                "strength": 75,
                "weight": weight,
                "reason": "Price touching/below lower band",
            }
        elif self.price >= upper:
            return {
                "name": "Bollinger Bands",
                "value": f"${self.price:.2f} at upper band",
                "signal": "SELL",
                "strength": 75,
                "weight": weight,
                "reason": "Price touching/above upper band",
            }
        else:
            return {
                "name": "Bollinger Bands",
                "value": f"${self.price:.2f} in middle",
                "signal": "HOLD",
                "strength": 0,
                "weight": weight,
                "reason": "Price within normal range",
            }

    def _analyze_volume(self, vol_ratio: float) -> Dict:
        """Analyze Volume"""
        weight = self._get_weight("VOLUME", 0.10)

        if vol_ratio > 1.5:
            return {
                "name": "Volume",
                "value": f"{vol_ratio:.2f}x average",
                "signal": "CONFIRM",
                "strength": 70,
                "weight": weight,
                "reason": "High volume confirms trend",
            }
        elif vol_ratio < 0.5:
            return {
                "name": "Volume",
                "value": f"{vol_ratio:.2f}x average",
                "signal": "WEAK",
                "strength": 30,
                "weight": weight,
                "reason": "Low volume weakens signal",
            }
        else:
            return {
                "name": "Volume",
                "value": f"{vol_ratio:.2f}x average",
                "signal": "NEUTRAL",
                "strength": 0,
                "weight": weight,
                "reason": "Normal volume",
            }

    def _analyze_peak_hilo(self, direction: str, alignment: int) -> Dict:
        """Analyze Peak HiLo multi-timeframe trend indicator"""
        weight = self._get_weight("PEAK_HILO", 0.20)

        if direction == "LONG" and alignment >= 75:
            return {
                "name": "Peak HiLo",
                "value": f"{alignment}% aligned LONG",
                "signal": "BUY",
                "strength": min(100, alignment),
                "weight": weight,
                "reason": f"Strong multi-timeframe uptrend ({alignment}% alignment)",
            }
        elif direction == "SHORT" and alignment >= 75:
            return {
                "name": "Peak HiLo",
                "value": f"{alignment}% aligned SHORT",
                "signal": "SELL",
                "strength": min(100, alignment),
                "weight": weight,
                "reason": f"Strong multi-timeframe downtrend ({alignment}% alignment)",
            }
        elif direction == "LONG" and alignment >= 50:
            return {
                "name": "Peak HiLo",
                "value": f"{alignment}% aligned LONG",
                "signal": "BUY",
                "strength": alignment,
                "weight": weight,
                "reason": f"Moderate multi-timeframe uptrend ({alignment}% alignment)",
            }
        elif direction == "SHORT" and alignment >= 50:
            return {
                "name": "Peak HiLo",
                "value": f"{alignment}% aligned SHORT",
                "signal": "SELL",
                "strength": alignment,
                "weight": weight,
                "reason": f"Moderate multi-timeframe downtrend ({alignment}% alignment)",
            }
        else:
            return {
                "name": "Peak HiLo",
                "value": f"{alignment}% aligned {direction}",
                "signal": "HOLD",
                "strength": 0,
                "weight": weight,
                "reason": f"Weak multi-timeframe alignment ({alignment}%)",
            }

    def _aggregate_signals(self, signals: List[Dict]) -> Dict:
        """Aggregate all indicator signals into overall signal"""
        buy_score = 0
        sell_score = 0
        total_weight = 0

        for sig in signals:
            if sig["signal"] == "BUY":
                buy_score += sig["strength"] * sig["weight"]
            elif sig["signal"] == "SELL":
                sell_score += sig["strength"] * sig["weight"]

            if sig["signal"] in ["BUY", "SELL"]:
                total_weight += sig["weight"]

        # Overall signal
        if buy_score > sell_score and buy_score > 50:
            signal = "BUY"
            strength = buy_score
        elif sell_score > buy_score and sell_score > 50:
            signal = "SELL"
            strength = sell_score
        else:
            signal = "HOLD"
            strength = max(buy_score, sell_score)

        # Confidence based on agreement between indicators
        agreement = len([s for s in signals if s["signal"] == signal]) / len(signals) if signals else 0
        confidence = int(agreement * 100)

        return {"signal": signal, "strength": int(strength), "confidence": confidence}

    def _generate_reasoning(self, signals: List[Dict]) -> List[str]:
        """Generate human-readable reasoning"""
        reasons = []
        for sig in signals:
            if sig["signal"] in ["BUY", "SELL"] and sig["strength"] > 0:
                strength_label = self._strength_label(sig["strength"])
                reasons.append(
                    f"• {sig['name']} ({sig['value']}): {sig['reason']} → {sig['signal']} ({strength_label})"
                )
        return reasons

    def _strength_label(self, strength: int) -> str:
        """Convert numeric strength to label"""
        if strength >= 75:
            return "Strong"
        elif strength >= 50:
            return "Medium"
        else:
            return "Weak"


# ========== CONVENIENCE FUNCTIONS ==========


def quick_analysis(
    prices: List[float], volumes: Optional[List[float]] = None, current_price: Optional[float] = None
) -> Dict:
    """
    Quick analysis of price data

    Args:
        prices: List of historical prices
        volumes: List of historical volumes (optional)
        current_price: Current price (defaults to last price)

    Returns:
        Analysis dict with signal, strength, confidence, reasoning
    """
    if not current_price:
        current_price = prices[-1]

    ind = TechnicalIndicators(prices, volumes)
    sig = SignalGenerator(ind, current_price)
    return sig.analyze_all()


if __name__ == "__main__":
    # Test with sample data
    logging.basicConfig(level=logging.DEBUG)

    print("🧪 Testing Technical Indicators\n")

    # Sample price data (50 days)
    prices = [
        100,
        101,
        99,
        102,
        103,
        105,
        104,
        106,
        108,
        107,
        109,
        111,
        110,
        112,
        114,
        113,
        115,
        117,
        116,
        118,
        120,
        119,
        121,
        123,
        122,
        124,
        126,
        125,
        127,
        129,
        128,
        130,
        132,
        131,
        133,
        135,
        134,
        136,
        138,
        137,
        139,
        141,
        140,
        138,
        136,
        134,
        132,
        130,
        128,
        126,
    ]

    volumes = [1000 + (i * 10) for i in range(len(prices))]

    # Run analysis
    result = quick_analysis(prices, volumes)

    print(f"Signal: {result['signal']}")
    print(f"Strength: {result['strength']}%")
    print(f"Confidence: {result['confidence']}%")
    print("\nReasoning:")
    for reason in result["reasoning"]:
        print(reason)
    print("\n✅ Test complete!")
