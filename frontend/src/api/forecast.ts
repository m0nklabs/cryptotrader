/**
 * TimesFM forecast API client.
 *
 * Fixed endpoint contract (backend built in parallel):
 * - POST /api/forecast        {symbol, timeframe, horizon} -> ForecastResponse
 * - POST /api/forecast/batch  {symbols[], timeframe, horizon} -> ForecastResponse[]
 * - GET  /api/forecast/status -> ForecastStatus
 *
 * Errors: 4xx responses carry `{detail: string}` (e.g. fewer than 32 candles
 * available); the message is surfaced to the caller as an Error.
 */

import { DEFAULT_API_TIMEOUT_MS } from '../lib/apiConfig'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ForecastPoint = {
  ts: string
  p10: number
  p50: number
  p90: number
}

export type ForecastResponse = {
  symbol: string
  timeframe: string
  horizon: number
  model_id: string
  generated_at: string
  points: ForecastPoint[]
  cache: 'hit' | 'miss'
  latency_ms: number
}

export type ForecastStatus = {
  loaded: boolean
  model_id: string
  device: string
  ready: boolean
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

const API_BASE = '/api'

// First model load + inference can be slow (TimesFM runs on the backend);
// allow up to 2 minutes like the backtest runner.
const FORECAST_TIMEOUT_MS = 120000

/**
 * Extract a human-readable message from an error response.
 * The contract is `{detail: string}`; be defensive about other shapes.
 */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown }
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail
    }
    if (
      payload.detail &&
      typeof payload.detail === 'object' &&
      'message' in payload.detail &&
      typeof (payload.detail as { message?: unknown }).message === 'string'
    ) {
      return (payload.detail as { message: string }).message
    }
  } catch {
    // Response body was not JSON; fall through to the generic message.
  }
  return `Forecast request failed: ${response.status} ${response.statusText}`
}

async function postForecast<T>(path: string, body: unknown): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), FORECAST_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(await readErrorMessage(response))
    }

    return (await response.json()) as T
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Run a TimesFM forecast for a single symbol.
 */
export async function runForecast(
  symbol: string,
  timeframe: string,
  horizon: number
): Promise<ForecastResponse> {
  return postForecast<ForecastResponse>('/forecast', { symbol, timeframe, horizon })
}

/**
 * Run TimesFM forecasts for a batch of symbols (one response per symbol).
 */
export async function runForecastBatch(
  symbols: string[],
  timeframe: string,
  horizon: number
): Promise<ForecastResponse[]> {
  return postForecast<ForecastResponse[]>('/forecast/batch', { symbols, timeframe, horizon })
}

/**
 * Check whether the TimesFM model is loaded and ready.
 */
export async function getForecastStatus(): Promise<ForecastStatus> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE}/forecast/status`, {
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(await readErrorMessage(response))
    }

    return (await response.json()) as ForecastStatus
  } finally {
    clearTimeout(timeoutId)
  }
}
