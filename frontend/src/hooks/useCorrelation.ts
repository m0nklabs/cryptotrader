/**
 * Correlation Hook
 * ================
 * React Query hook for fetching asset correlation data
 */

import { useEffect, useState } from 'react'

export type CorrelationData = {
  symbols: string[]
  matrix: number[][]
  lookback_days: number
  data_points: number
  start_time: string | null
  end_time: string | null
}

export function useCorrelation(
  symbols: string[],
  exchange: string = 'bitfinex',
  timeframe: string = '1d',
  lookbackDays: number = 30
) {
  const [data, setData] = useState<CorrelationData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (symbols.length < 2) {
      setData(null)
      return
    }

    let mounted = true
    const controller = new AbortController()

    const fetchCorrelation = async () => {
      setLoading(true)
      setError(null)

      try {
        const symbolsParam = symbols.join(',')
        const url = `/api/correlation?symbols=${encodeURIComponent(symbolsParam)}&exchange=${encodeURIComponent(exchange)}&timeframe=${encodeURIComponent(timeframe)}&lookback=${lookbackDays}`

        const response = await fetch(url, { signal: controller.signal })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || `HTTP ${response.status}`)
        }

        const result = await response.json()

        if (mounted) {
          setData(result)
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          return
        }
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to fetch correlation')
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    fetchCorrelation()

    return () => {
      mounted = false
      controller.abort()
    }
  }, [symbols.join(','), exchange, timeframe, lookbackDays])

  return { data, loading, error }
}
