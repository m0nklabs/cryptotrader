import { DEFAULT_API_TIMEOUT_MS } from '../lib/apiConfig'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type BacktestStrategy = 'rsi' | 'sma'

export type StrategyInfo = {
  name: BacktestStrategy
  description: string
  parameters: Record<string, {
    type: string
    default: number
    min?: number
    max?: number
    description: string
  }>
}

export type Trade = {
  entry_price: string
  exit_price: string
  side: string
  size: string
  pnl: string
}

export type BacktestRequest = {
  exchange?: string
  symbol: string
  timeframe?: string
  strategy: BacktestStrategy
  start_date?: string
  end_date?: string
  initial_capital?: number
  rsi_oversold?: number
  rsi_overbought?: number
  sma_fast_period?: number
  sma_slow_period?: number
}

export type BacktestResult = {
  exchange: string
  symbol: string
  timeframe: string
  strategy: string
  start_date: string
  end_date: string
  initial_capital: number
  total_pnl: number
  total_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  num_trades: number
  trades: Trade[]
  equity_curve: number[]
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/**
 * List available backtest strategies
 */
export async function listStrategies(): Promise<StrategyInfo[]> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE}/backtest/strategies`, {
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(`Failed to fetch strategies: ${response.statusText}`)
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Run a backtest
 */
export async function runBacktest(
  request: BacktestRequest
): Promise<BacktestResult> {
  const controller = new AbortController()
  // Backtests can take longer, use 2 minutes timeout
  const timeoutId = setTimeout(() => controller.abort(), 120000)

  try {
    const response = await fetch(`${API_BASE}/backtest/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail?.message || `Backtest failed: ${response.statusText}`)
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}
