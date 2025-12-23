/**
 * Technical indicator calculations for candlestick chart analysis.
 * All calculations use close prices unless specified otherwise.
 */

export type Candle = {
  t: number
  o: number
  h: number
  l: number
  c: number
  v: number
}

/**
 * Simple Moving Average (SMA)
 * Returns an array of the same length as input, with null for insufficient data points.
 */
export function calculateSMA(candles: Candle[], period: number): (number | null)[] {
  if (!candles.length || period < 1 || !Number.isInteger(period)) {
    return candles.map(() => null)
  }
  
  const result: (number | null)[] = []
  
  for (let i = 0; i < candles.length; i++) {
    if (i < period - 1) {
      result.push(null)
      continue
    }
    
    let sum = 0
    for (let j = 0; j < period; j++) {
      sum += candles[i - j].c
    }
    result.push(sum / period)
  }
  
  return result
}

/**
 * Exponential Moving Average (EMA)
 * Returns an array of the same length as input, with null for insufficient data points.
 */
export function calculateEMA(candles: Candle[], period: number): (number | null)[] {
  if (!candles.length || period < 1 || !Number.isInteger(period)) {
    return candles.map(() => null)
  }
  
  const result: (number | null)[] = []
  const k = 2 / (period + 1)
  
  let ema: number | null = null
  
  for (let i = 0; i < candles.length; i++) {
    if (ema === null) {
      // Initialize with SMA for first 'period' candles
      if (i < period - 1) {
        result.push(null)
        continue
      }
      
      let sum = 0
      for (let j = 0; j < period; j++) {
        sum += candles[i - j].c
      }
      ema = sum / period
      result.push(ema)
    } else {
      ema = candles[i].c * k + ema * (1 - k)
      result.push(ema)
    }
  }
  
  return result
}

/**
 * Relative Strength Index (RSI)
 * Returns an array of the same length as input, with null for insufficient data points.
 */
export function calculateRSI(candles: Candle[], period: number = 14): (number | null)[] {
  const result: (number | null)[] = []
  
  if (candles.length < period + 1) {
    return candles.map(() => null)
  }
  
  // Calculate initial average gain and loss
  let avgGain = 0
  let avgLoss = 0
  
  for (let i = 1; i <= period; i++) {
    const change = candles[i].c - candles[i - 1].c
    if (change > 0) {
      avgGain += change
    } else {
      avgLoss += Math.abs(change)
    }
  }
  
  avgGain /= period
  avgLoss /= period
  
  // First 'period' values are null
  for (let i = 0; i < period; i++) {
    result.push(null)
  }
  
  // Calculate RSI using smoothed averages
  for (let i = period; i < candles.length; i++) {
    const change = candles[i].c - candles[i - 1].c
    const gain = change > 0 ? change : 0
    const loss = change < 0 ? Math.abs(change) : 0
    
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    
    if (avgLoss === 0) {
      result.push(100)
    } else {
      const rs = avgGain / avgLoss
      const rsi = 100 - 100 / (1 + rs)
      result.push(rsi)
    }
  }
  
  return result
}

/**
 * MACD (Moving Average Convergence Divergence)
 * Returns MACD line, signal line, and histogram.
 */
export function calculateMACD(
  candles: Candle[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9
): {
  macd: (number | null)[]
  signal: (number | null)[]
  histogram: (number | null)[]
} {
  if (
    !candles.length ||
    fastPeriod < 1 || !Number.isInteger(fastPeriod) ||
    slowPeriod < 1 || !Number.isInteger(slowPeriod) ||
    signalPeriod < 1 || !Number.isInteger(signalPeriod) ||
    fastPeriod >= slowPeriod
  ) {
    const empty = candles.map(() => null)
    return { macd: empty, signal: empty, histogram: empty }
  }
  
  const fastEMA = calculateEMA(candles, fastPeriod)
  const slowEMA = calculateEMA(candles, slowPeriod)
  
  // Calculate MACD line (fastEMA - slowEMA)
  const macd: (number | null)[] = []
  for (let i = 0; i < candles.length; i++) {
    if (fastEMA[i] === null || slowEMA[i] === null) {
      macd.push(null)
    } else {
      macd.push(fastEMA[i]! - slowEMA[i]!)
    }
  }
  
  // Calculate signal line (EMA of MACD)
  const signal: (number | null)[] = []
  const k = 2 / (signalPeriod + 1)
  let signalEMA: number | null = null
  let validCount = 0
  
  for (let i = 0; i < macd.length; i++) {
    if (macd[i] === null) {
      signal.push(null)
      continue
    }
    
    if (signalEMA === null) {
      validCount++
      if (validCount < signalPeriod) {
        signal.push(null)
        continue
      }
      
      // Initialize signal with SMA of first 'signalPeriod' MACD values
      let sum = 0
      for (let j = 0; j < signalPeriod; j++) {
        sum += macd[i - j]!
      }
      signalEMA = sum / signalPeriod
      signal.push(signalEMA)
    } else {
      signalEMA = macd[i]! * k + signalEMA * (1 - k)
      signal.push(signalEMA)
    }
  }
  
  // Calculate histogram (MACD - signal)
  const histogram: (number | null)[] = []
  for (let i = 0; i < candles.length; i++) {
    if (macd[i] === null || signal[i] === null) {
      histogram.push(null)
    } else {
      histogram.push(macd[i]! - signal[i]!)
    }
  }
  
  return { macd, signal, histogram }
}
