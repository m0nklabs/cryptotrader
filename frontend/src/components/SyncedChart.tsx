/**
 * Synced Chart Component
 * ======================
 * Individual chart with crosshair synchronization
 */

import { useEffect, useRef } from 'react'
import {
  createChart,
  CandlestickSeries,
  type IChartApi,
  ColorType,
  type CandlestickData,
} from 'lightweight-charts'
import { useCrosshairSync } from '../hooks/useCrosshairSync'
import type { OHLCV } from '../utils/indicators'

const CHART_COLORS = {
  background: '#0f172a',
  textColor: '#94a3b8',
  gridColor: '#1e293b',
  upColor: '#22c55e',
  downColor: '#ef4444',
  borderUpColor: '#22c55e',
  borderDownColor: '#ef4444',
  wickUpColor: '#22c55e',
  wickDownColor: '#ef4444',
}

type Props = {
  chartId: string
  symbol: string
  timeframe: string
  candles: OHLCV[]
  height?: number
}

export default function SyncedChart({
  chartId,
  symbol,
  timeframe,
  candles,
  height = 300,
}: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartApi = useRef<IChartApi | null>(null)
  const candleSeries = useRef<ReturnType<IChartApi['addSeries']> | null>(null)

  // Use crosshair synchronization
  useCrosshairSync(chartApi.current, chartId)

  // Create chart
  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.textColor,
      },
      grid: {
        vertLines: { color: CHART_COLORS.gridColor },
        horzLines: { color: CHART_COLORS.gridColor },
      },
      width: chartRef.current.clientWidth,
      height,
      crosshair: {
        mode: 1, // Normal crosshair
      },
      timeScale: {
        borderColor: CHART_COLORS.gridColor,
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: CHART_COLORS.gridColor,
      },
    })

    chartApi.current = chart

    // Add candlestick series
    const series = chart.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.upColor,
      downColor: CHART_COLORS.downColor,
      borderUpColor: CHART_COLORS.borderUpColor,
      borderDownColor: CHART_COLORS.borderDownColor,
      wickUpColor: CHART_COLORS.wickUpColor,
      wickDownColor: CHART_COLORS.wickDownColor,
    })
    candleSeries.current = series

    // Handle resize
    const handleResize = () => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartApi.current = null
      candleSeries.current = null
    }
  }, [height])

  // Update candle data
  useEffect(() => {
    if (!candleSeries.current || candles.length === 0) return

    const data: CandlestickData[] = candles.map((c) => ({
      time: c.time as CandlestickData['time'],
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))

    candleSeries.current.setData(data)
    chartApi.current?.timeScale().fitContent()
  }, [candles])

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span className="font-semibold">
          {symbol} · {timeframe}
        </span>
      </div>
      <div ref={chartRef} className="w-full rounded border border-gray-800" />
    </div>
  )
}
