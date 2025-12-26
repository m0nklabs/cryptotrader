/**
 * Opportunity Score Component
 * ===========================
 * Displays opportunity score with color coding and explainability
 */

import { useEffect, useState } from 'react'
import { fetchSignal, fetchSignalHistory, type OpportunitySignal, type SignalHistory } from '../api/signals'
import SignalBreakdown from './SignalBreakdown'

type Props = {
  symbol: string
  exchange?: string
}

export default function OpportunityScore({ symbol, exchange = 'bitfinex' }: Props) {
  const [signal, setSignal] = useState<OpportunitySignal | null>(null)
  const [history, setHistory] = useState<SignalHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [breakdownExpanded, setBreakdownExpanded] = useState(false)

  useEffect(() => {
    let mounted = true

    const load = async () => {
      setLoading(true)
      setError(null)

      try {
        const [currentSignal, signalHistory] = await Promise.all([
          fetchSignal(symbol, exchange),
          fetchSignalHistory(symbol, exchange, 24),
        ])

        if (mounted) {
          setSignal(currentSignal)
          setHistory(signalHistory)
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load signal')
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    load()
    const interval = setInterval(load, 30_000) // Refresh every 30s

    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [symbol, exchange])

  if (loading && !signal) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
        Loading signal...
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded border border-red-800 bg-red-900/20 p-4 text-center text-sm text-red-400">
        {error}
      </div>
    )
  }

  if (!signal) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
        No signal available for {symbol}
      </div>
    )
  }

  // Color coding based on score
  const scoreColor =
    signal.score >= 61
      ? 'text-green-500'
      : signal.score >= 31
        ? 'text-yellow-500'
        : 'text-red-500'

  const scoreBg =
    signal.score >= 61
      ? 'bg-green-500/10 border-green-500/30'
      : signal.score >= 31
        ? 'bg-yellow-500/10 border-yellow-500/30'
        : 'bg-red-500/10 border-red-500/30'

  const directionIcon =
    signal.side === 'BUY' ? '↑' : signal.side === 'SELL' ? '↓' : '—'

  const lastUpdate = new Date(signal.created_at).toLocaleTimeString()

  return (
    <div className="flex flex-col gap-3">
      {/* Score display */}
      <div className={`flex items-center justify-between rounded-lg border p-4 ${scoreBg}`}>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-gray-400">Opportunity Score</span>
          <div className="flex items-baseline gap-2">
            <span className={`text-4xl font-bold ${scoreColor}`}>{signal.score}</span>
            <span className="text-xl text-gray-500">/100</span>
          </div>
        </div>

        <div className="flex flex-col items-end gap-1">
          <div className={`flex items-center gap-1 text-2xl ${scoreColor}`}>
            <span>{directionIcon}</span>
            <span className="text-sm font-medium">{signal.side}</span>
          </div>
          <span className="text-xs text-gray-500">Updated: {lastUpdate}</span>
        </div>
      </div>

      {/* Sparkline */}
      {history.length > 0 && (
        <div className="rounded border border-gray-800 bg-gray-900 p-2">
          <div className="mb-1 text-xs text-gray-400">Score History (24 points)</div>
          <div className="flex h-12 items-end gap-0.5">
            {history.slice().reverse().map((h, idx) => {
              const height = (h.score / 100) * 100
              const color =
                h.score >= 61 ? 'bg-green-500' : h.score >= 31 ? 'bg-yellow-500' : 'bg-red-500'

              return (
                <div
                  key={idx}
                  className={`flex-1 rounded-sm ${color} opacity-70 hover:opacity-100`}
                  style={{ height: `${height}%` }}
                  title={`Score: ${h.score}, Side: ${h.side}`}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Signal breakdown */}
      <SignalBreakdown
        signals={signal.signals}
        isExpanded={breakdownExpanded}
        onToggle={() => setBreakdownExpanded(!breakdownExpanded)}
      />
    </div>
  )
}
