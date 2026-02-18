/**
 * API client for alerts system.
 */

import { DEFAULT_API_TIMEOUT_MS } from '../lib/apiConfig'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AlertType =
  | 'price_above'
  | 'price_below'
  | 'rsi_overbought'
  | 'rsi_oversold'
  | 'macd_cross_up'
  | 'macd_cross_down'

export type ComparisonOperator = 'above' | 'below' | 'crosses_above' | 'crosses_below'

export type AlertCondition = {
  type: AlertType
  operator: ComparisonOperator
  value: number
  indicator_params?: Record<string, number>
}

export type Alert = {
  id: number
  symbol: string
  exchange: string
  timeframe: string
  condition_type: AlertType
  operator: ComparisonOperator
  threshold_value: number
  indicator_params: Record<string, number> | null
  enabled: boolean
  created_at: string
  triggered_at: string | null
  trigger_count: number
}

export type AlertHistory = {
  id: number
  alert_id: number
  triggered_at: string
  trigger_value: number
  price: number
  message: string
}

export type CreateAlertRequest = {
  symbol: string
  exchange: string
  timeframe: string
  condition: AlertCondition
  enabled?: boolean
}

export type UpdateAlertRequest = {
  enabled?: boolean
  threshold_value?: number
  indicator_params?: Record<string, number>
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

/**
 * Create a new alert.
 */
export async function createAlert(request: CreateAlertRequest): Promise<Alert> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch('/alerts/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Failed to create alert' }))
      throw new Error(error.detail || error.error || 'Failed to create alert')
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * List all alerts with optional filtering.
 */
export async function listAlerts(params?: {
  symbol?: string
  exchange?: string
  enabled_only?: boolean
}): Promise<{ alerts: Alert[]; count: number }> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const queryParams = new URLSearchParams()
    if (params?.symbol) queryParams.set('symbol', params.symbol)
    if (params?.exchange) queryParams.set('exchange', params.exchange)
    if (params?.enabled_only) queryParams.set('enabled_only', 'true')

    const url = `/alerts/${queryParams.toString() ? '?' + queryParams.toString() : ''}`
    const response = await fetch(url, { signal: controller.signal })

    if (!response.ok) {
      throw new Error('Failed to fetch alerts')
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Get a specific alert by ID.
 */
export async function getAlert(alertId: number): Promise<Alert> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch(`/alerts/${alertId}`, { signal: controller.signal })

    if (!response.ok) {
      throw new Error('Alert not found')
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Update an alert.
 */
export async function updateAlert(alertId: number, request: UpdateAlertRequest): Promise<Alert> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch(`/alerts/${alertId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Failed to update alert' }))
      throw new Error(error.detail || error.error || 'Failed to update alert')
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Delete an alert.
 */
export async function deleteAlert(alertId: number): Promise<void> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch(`/alerts/${alertId}`, {
      method: 'DELETE',
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error('Failed to delete alert')
    }
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Get alert history for a specific alert.
 */
export async function getAlertHistory(
  alertId: number,
  limit = 100
): Promise<{ history: AlertHistory[]; count: number }> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch(`/alerts/${alertId}/history?limit=${limit}`, {
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error('Failed to fetch alert history')
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Get all alert history.
 */
export async function getAllAlertHistory(
  limit = 100
): Promise<{ history: AlertHistory[]; count: number }> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_API_TIMEOUT_MS)

  try {
    const response = await fetch(`/alerts/history/all?limit=${limit}`, {
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error('Failed to fetch alert history')
    }

    return await response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}
