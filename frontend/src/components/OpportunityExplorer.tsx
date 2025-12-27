/**
 * Opportunity Explorer Component
 * ===============================
 * List/table of trading opportunities sorted by quality
 */

import { useEffect, useState, useCallback } from 'react'
import type { OpportunitySignal } from '../api/signals'

type Props = {
  exchange?: string
  onSelectOpportunity?: (symbol: string, timeframe: string) => void
}

type SortKey = 'score' | 'symbol' | 'timeframe' | 'timestamp'
type SortDirection = 'asc' | 'desc'

export default function OpportunityExplorer({ exchange = 'bitfinex', onSelectOpportunity }: Props) {
  const [opportunities, setOpportunities] = useState<OpportunitySignal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [filter, setFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL')

  // Fetch opportunities
  useEffect(() => {
    let mounted = true

    const load = async () => {
      setLoading(true)
      setError(null)

      try {
        const response = await fetch(
          `/api/signals?exchange=${encodeURIComponent(exchange)}&limit=50`
        )

        if (!response.ok) {
          throw new Error(`Failed to fetch opportunities: ${response.status}`)
        }

        const data = await response.json()
        if (mounted) {
          setOpportunities(data.signals || [])
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load opportunities')
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
  }, [exchange])

  // Sort and filter
  const filteredAndSorted = useCallback(() => {
    let result = [...opportunities]

    // Filter by side
    if (filter !== 'ALL') {
      result = result.filter((opp) => opp.side === filter)
    }

    // Sort comparator functions
    const compareNumbers = (a: number, b: number) =>
      sortDirection === 'asc' ? a - b : b - a

    const compareStrings = (a: string, b: string) =>
      sortDirection === 'asc' ? a.localeCompare(b) : b.localeCompare(a)

    // Sort with type-safe comparisons
    result.sort((a, b) => {
      if (sortKey === 'timestamp') {
        return compareNumbers(a.created_at, b.created_at)
      } else if (sortKey === 'score') {
        return compareNumbers(a.score, b.score)
      } else if (sortKey === 'symbol') {
        return compareStrings(a.symbol, b.symbol)
      } else if (sortKey === 'timeframe') {
        return compareStrings(a.timeframe, b.timeframe)
      }
      return 0
    })

    return result
  }, [opportunities, filter, sortKey, sortDirection])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDirection('desc')
    }
  }

  const handleSelect = (opp: OpportunitySignal) => {
    if (onSelectOpportunity) {
      onSelectOpportunity(opp.symbol, opp.timeframe)
    }
  }

  const getScoreColor = (score: number) => {
    if (score >= 61) return 'text-green-500'
    if (score >= 31) return 'text-yellow-500'
    return 'text-red-500'
  }

  const getSideBg = (side: string) => {
    if (side === 'BUY') return 'bg-green-500/10 border-green-500/30'
    if (side === 'SELL') return 'bg-red-500/10 border-red-500/30'
    return 'bg-gray-500/10 border-gray-500/30'
  }

  if (loading && opportunities.length === 0) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
        Loading opportunities...
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

  const sortedOpportunities = filteredAndSorted()

  return (
    <div className="flex flex-col gap-2">
      {/* Controls */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-1">
          {(['ALL', 'BUY', 'SELL'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-500">
          {sortedOpportunities.length} opportunities
        </span>
      </div>

      {/* Table */}
      <div className="overflow-auto rounded border border-gray-800">
        <table className="w-full text-xs">
          <thead className="bg-gray-900 text-gray-400">
            <tr>
              <th
                className="cursor-pointer p-2 text-left hover:bg-gray-800"
                onClick={() => handleSort('score')}
              >
                Score {sortKey === 'score' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th
                className="cursor-pointer p-2 text-left hover:bg-gray-800"
                onClick={() => handleSort('symbol')}
              >
                Symbol {sortKey === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th
                className="cursor-pointer p-2 text-left hover:bg-gray-800"
                onClick={() => handleSort('timeframe')}
              >
                Timeframe {sortKey === 'timeframe' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th className="p-2 text-left">Side</th>
              <th className="p-2 text-left">Signals</th>
              <th
                className="cursor-pointer p-2 text-left hover:bg-gray-800"
                onClick={() => handleSort('timestamp')}
              >
                Time {sortKey === 'timestamp' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedOpportunities.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-4 text-center text-gray-500">
                  No opportunities found
                </td>
              </tr>
            ) : (
              sortedOpportunities.map((opp) => (
                <tr
                  key={`${opp.symbol}-${opp.timeframe}-${opp.created_at}`}
                  className="cursor-pointer border-t border-gray-800 hover:bg-gray-800/50"
                  onClick={() => handleSelect(opp)}
                >
                  <td className="p-2">
                    <span className={`font-bold ${getScoreColor(opp.score)}`}>
                      {opp.score}
                    </span>
                  </td>
                  <td className="p-2 font-semibold text-gray-200">{opp.symbol}</td>
                  <td className="p-2 text-gray-400">{opp.timeframe}</td>
                  <td className="p-2">
                    <span className={`rounded border px-2 py-0.5 text-xs ${getSideBg(opp.side)}`}>
                      {opp.side}
                    </span>
                  </td>
                  <td className="p-2 text-gray-400">{opp.signals.length}</td>
                  <td className="p-2 text-gray-500">
                    {new Date(opp.created_at).toLocaleTimeString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
