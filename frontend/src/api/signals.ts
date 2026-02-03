/**
 * Signal API Client
 * =================
 * Client for fetching opportunity signals and scores
 */

import { DEFAULT_API_TIMEOUT_MS } from '../lib/apiConfig'

export type SignalDetail = {
  code: string
  side: string
  strength: number
  value: string
  reason: string
}

export type OpportunitySignal = {
  symbol: string
  timeframe: string
  score: number
  side: string
  signals: SignalDetail[]
  created_at: number
}

export type SignalHistory = {
  timestamp: number
  score: number
  side: string
}

/**
 * Fetch current signal and breakdown for a symbol
 */
export async function fetchSignal(
  symbol: string,
  exchange: string = 'bitfinex',
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS
): Promise<OpportunitySignal | null> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(
      `/api/signals?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(symbol)}&limit=1`,
      { signal: controller.signal }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch signal: ${response.status}`)
    }

    const data = await response.json()
    if (!data.signals || !Array.isArray(data.signals) || data.signals.length === 0) {
      return null
    }

    return data.signals[0]
  } finally {
    // Cleanup timeout to ensure no lingering timers
    clearTimeout(timeoutId)
  }
}

/**
 * Fetch signal history for sparkline
 */
export async function fetchSignalHistory(
  symbol: string,
  exchange: string = 'bitfinex',
  limit: number = 24,
  timeoutMs: number = DEFAULT_API_TIMEOUT_MS
): Promise<SignalHistory[]> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(
      `/api/signals?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(symbol)}&limit=${limit}`,
      { signal: controller.signal }
    )

    if (!response.ok) {
      throw new Error(`Failed to fetch signal history: ${response.status}`)
    }

    const data = await response.json()
    if (!data.signals || !Array.isArray(data.signals)) {
      return []
    }

    return data.signals.map((sig: OpportunitySignal) => ({
      timestamp: sig.created_at,
      score: sig.score,
      side: sig.side,
    }))
  } finally {
    clearTimeout(timeoutId)
  }
}
