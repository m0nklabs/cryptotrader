/**
 * Technical Indicator Calculations
 * ================================
 * Client-side implementations of MACD, Bollinger Bands, Stochastic, RSI, ATR
 */

export type OHLCV = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// =============================================================================
// EMA / SMA Helpers
// =============================================================================

export function sma(values: number[], period: number): number[] {
  const result: number[] = []
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) {
      result.push(NaN)
    } else {
      const slice = values.slice(i - period + 1, i + 1)
      result.push(slice.reduce((a, b) => a + b, 0) / period)
    }
  }
  return result
}

export function ema(values: number[], period: number): number[] {
  const result: number[] = []
  const multiplier = 2 / (period + 1)

  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) {
      result.push(NaN)
    } else if (i === period - 1) {
      // First EMA is SMA
      const slice = values.slice(0, period)
      result.push(slice.reduce((a, b) => a + b, 0) / period)
    } else {
      const prev = result[i - 1]
      result.push((values[i] - prev) * multiplier + prev)
    }
  }
  return result
}

// =============================================================================
// RSI - Relative Strength Index
// =============================================================================

export type RSIResult = {
  time: number
  value: number
}[]

export function calculateRSI(candles: OHLCV[], period = 14): RSIResult {
  if (candles.length < period + 1) return []

  const closes = candles.map((c) => c.close)
  const changes: number[] = []

  for (let i = 1; i < closes.length; i++) {
    changes.push(closes[i] - closes[i - 1])
  }

  const result: RSIResult = []

  // Calculate initial average gain/loss
  let avgGain = 0
  let avgLoss = 0

  for (let i = 0; i < period; i++) {
    if (changes[i] > 0) avgGain += changes[i]
    else avgLoss += Math.abs(changes[i])
  }

  avgGain /= period
  avgLoss /= period

  // First RSI value
  const firstRS = avgLoss === 0 ? 100 : avgGain / avgLoss
  const firstRSI = 100 - 100 / (1 + firstRS)
  result.push({ time: candles[period].time, value: firstRSI })

  // Smoothed RSI for remaining
  for (let i = period; i < changes.length; i++) {
    const change = changes[i]
    const gain = change > 0 ? change : 0
    const loss = change < 0 ? Math.abs(change) : 0

    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period

    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
    const rsi = 100 - 100 / (1 + rs)
    result.push({ time: candles[i + 1].time, value: rsi })
  }

  return result
}

// =============================================================================
// MACD - Moving Average Convergence Divergence
// =============================================================================

export type MACDResult = {
  time: number
  macd: number
  signal: number
  histogram: number
}[]

export function calculateMACD(
  candles: OHLCV[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9
): MACDResult {
  if (candles.length < slowPeriod + signalPeriod) return []

  const closes = candles.map((c) => c.close)
  const fastEMA = ema(closes, fastPeriod)
  const slowEMA = ema(closes, slowPeriod)

  // MACD line = fast EMA - slow EMA
  const macdLine: number[] = []
  for (let i = 0; i < closes.length; i++) {
    if (isNaN(fastEMA[i]) || isNaN(slowEMA[i])) {
      macdLine.push(NaN)
    } else {
      macdLine.push(fastEMA[i] - slowEMA[i])
    }
  }

  // Signal line = EMA of MACD line
  const validMacd = macdLine.filter((v) => !isNaN(v))
  const signalEMA = ema(validMacd, signalPeriod)

  const result: MACDResult = []
  let signalIdx = 0

  for (let i = 0; i < candles.length; i++) {
    if (isNaN(macdLine[i])) continue

    if (signalIdx < signalPeriod - 1) {
      signalIdx++
      continue
    }

    const signal = signalEMA[signalIdx]
    if (isNaN(signal)) {
      signalIdx++
      continue
    }

    result.push({
      time: candles[i].time,
      macd: macdLine[i],
      signal: signal,
      histogram: macdLine[i] - signal,
    })
    signalIdx++
  }

  return result
}

// =============================================================================
// Bollinger Bands
// =============================================================================

export type BollingerResult = {
  time: number
  upper: number
  middle: number
  lower: number
}[]

export function calculateBollingerBands(
  candles: OHLCV[],
  period = 20,
  stdDev = 2
): BollingerResult {
  if (candles.length < period) return []

  const closes = candles.map((c) => c.close)
  const middleBand = sma(closes, period)

  const result: BollingerResult = []

  for (let i = period - 1; i < candles.length; i++) {
    const slice = closes.slice(i - period + 1, i + 1)
    const mean = middleBand[i]

    // Standard deviation
    const variance = slice.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / period
    const std = Math.sqrt(variance)

    result.push({
      time: candles[i].time,
      upper: mean + stdDev * std,
      middle: mean,
      lower: mean - stdDev * std,
    })
  }

  return result
}

// =============================================================================
// Stochastic Oscillator
// =============================================================================

export type StochasticResult = {
  time: number
  k: number
  d: number
}[]

export function calculateStochastic(
  candles: OHLCV[],
  kPeriod = 14,
  dPeriod = 3
): StochasticResult {
  if (candles.length < kPeriod + dPeriod - 1) return []

  const kValues: number[] = []

  // Calculate %K
  for (let i = kPeriod - 1; i < candles.length; i++) {
    const slice = candles.slice(i - kPeriod + 1, i + 1)
    const high = Math.max(...slice.map((c) => c.high))
    const low = Math.min(...slice.map((c) => c.low))
    const close = candles[i].close

    const k = high === low ? 50 : ((close - low) / (high - low)) * 100
    kValues.push(k)
  }

  // Calculate %D (SMA of %K)
  const dValues = sma(kValues, dPeriod)

  const result: StochasticResult = []

  for (let i = dPeriod - 1; i < kValues.length; i++) {
    if (isNaN(dValues[i])) continue

    result.push({
      time: candles[i + kPeriod - 1].time,
      k: kValues[i],
      d: dValues[i],
    })
  }

  return result
}

// =============================================================================
// ATR - Average True Range
// =============================================================================

export type ATRResult = {
  time: number
  value: number
}[]

export function calculateATR(candles: OHLCV[], period = 14): ATRResult {
  if (candles.length < period + 1) return []

  // True Range = max(high-low, |high-prevClose|, |low-prevClose|)
  const trueRanges: number[] = []

  for (let i = 1; i < candles.length; i++) {
    const high = candles[i].high
    const low = candles[i].low
    const prevClose = candles[i - 1].close

    const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose))
    trueRanges.push(tr)
  }

  const result: ATRResult = []

  // First ATR is SMA of true ranges
  let atr = trueRanges.slice(0, period).reduce((a, b) => a + b, 0) / period
  result.push({ time: candles[period].time, value: atr })

  // Smoothed ATR
  for (let i = period; i < trueRanges.length; i++) {
    atr = (atr * (period - 1) + trueRanges[i]) / period
    result.push({ time: candles[i + 1].time, value: atr })
  }

  return result
}
