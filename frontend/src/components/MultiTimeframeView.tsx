/**
 * Multi-Timeframe View Component
 * ===============================
 * Grid layout displaying multiple charts with synchronized crosshair
 */

import { useEffect, useState, useRef } from 'react'
import SyncedChart from './SyncedChart'
import { useMultiChartStore, type TimeframePreset } from '../stores/multiChartStore'
import type { OHLCV } from '../utils/indicators'

type Props = {
  symbol: string
  fetchCandles: (symbol: string, timeframe: string) => Promise<OHLCV[]>
}

export default function MultiTimeframeView({ symbol, fetchCandles }: Props) {
  const { charts, preset, applyPreset } = useMultiChartStore()
  const [candleData, setCandleData] = useState<Record<string, OHLCV[]>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Initialize with default preset and update when symbol changes
  const prevSymbolRef = useRef<string | null>(null)
  useEffect(() => {
    if (prevSymbolRef.current === symbol) {
      return
    }

    applyPreset('swing', symbol)
    prevSymbolRef.current = symbol
  }, [symbol, applyPreset])

  // Fetch candles for all visible charts
  useEffect(() => {
    const loadCandles = async () => {
      setLoading(true)
      setError(null)
      const newData: Record<string, OHLCV[]> = {}

      try {
        await Promise.all(
          charts
            .filter((chart) => chart.visible)
            .map(async (chart) => {
              try {
                const candles = await fetchCandles(chart.symbol, chart.timeframe)
                newData[chart.id] = candles
              } catch (err) {
                console.error(`Failed to fetch ${chart.symbol} ${chart.timeframe}:`, err)
              }
            })
        )
        setCandleData(newData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load candles')
      } finally {
        setLoading(false)
      }
    }

    if (charts.length > 0) {
      loadCandles()
    }
  }, [charts, symbol, fetchCandles])

  const handlePresetChange = (newPreset: TimeframePreset) => {
    applyPreset(newPreset, symbol)
  }

  const visibleCharts = charts.filter((c) => c.visible)
  const gridCols = visibleCharts.length === 2 ? 'grid-cols-2' :
                   visibleCharts.length === 3 ? 'grid-cols-3' :
                   visibleCharts.length >= 4 ? 'grid-cols-2' : 'grid-cols-1'

  return (
    <div className="flex flex-col gap-3">
      {/* Preset selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400">Timeframe Preset:</span>
        <div className="flex gap-1">
          {(['scalper', 'swing', 'position'] as TimeframePreset[]).map((p) => (
            <button
              key={p}
              onClick={() => handlePresetChange(p)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                preset === p
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300'
              }`}
            >
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Chart grid */}
      {loading && charts.length === 0 ? (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
          Loading charts...
        </div>
      ) : error ? (
        <div className="rounded border border-red-800 bg-red-900/20 p-4 text-center text-sm text-red-400">
          {error}
        </div>
      ) : visibleCharts.length > 0 ? (
        <div className={`grid ${gridCols} gap-3`}>
          {visibleCharts.map((chart) => (
            <SyncedChart
              key={chart.id}
              chartId={chart.id}
              symbol={chart.symbol}
              timeframe={chart.timeframe}
              candles={candleData[chart.id] || []}
              height={280}
            />
          ))}
        </div>
      ) : (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
          No charts configured
        </div>
      )}
    </div>
  )
}
