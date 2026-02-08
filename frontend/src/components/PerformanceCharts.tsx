import { useEffect, useMemo, useRef } from 'react'
import { ColorType, LineSeries, createChart, type LineData } from 'lightweight-charts'

export type EquityPoint = {
  time: number
  value: number
}

type Props = {
  equityCurve: EquityPoint[]
}

const CHART_BASE_OPTIONS = {
  layout: {
    background: { type: ColorType.Solid, color: '#0f172a' },
    textColor: '#94a3b8',
  },
  grid: {
    vertLines: { color: '#1e293b' },
    horzLines: { color: '#1e293b' },
  },
  timeScale: {
    borderColor: '#1e293b',
    timeVisible: true,
    secondsVisible: false,
  },
  rightPriceScale: {
    borderColor: '#1e293b',
  },
} as const

const SERIES_COLORS = {
  equity: '#22c55e',
  drawdown: '#ef4444',
}

// Minimal ResizeObserver polyfill for jsdom/test environments where it's undefined.
// Lightweight-charts only needs the API surface; layout isn't measured in tests.
const ensureResizeObserver = () => {
  if (typeof window === 'undefined') return
  if (typeof (window as { ResizeObserver?: unknown }).ResizeObserver === 'undefined') {
    ;(window as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
}

const normalizeEquity = (points: EquityPoint[]): EquityPoint[] =>
  points
    .filter((p) => Number.isFinite(p.value))
    .map((p, idx) => ({
      time: Number.isFinite(p.time) ? p.time : idx,
      value: p.value,
    }))

const toLineData = (points: EquityPoint[]): LineData[] =>
  normalizeEquity(points).map((p) => ({
    time: p.time,
    value: p.value,
  }))

const computeDrawdownSeries = (points: EquityPoint[]): EquityPoint[] => {
  if (!points.length) return []

  let peak = points[0].value
  return points.map((p) => {
    peak = Math.max(peak, p.value)
    const dd = peak > 0 ? ((p.value - peak) / peak) * 100 : 0
    return { time: p.time, value: Number(dd.toFixed(2)) }
  })
}

export default function PerformanceCharts({ equityCurve }: Props) {
  const equityRef = useRef<HTMLDivElement | null>(null)
  const drawdownRef = useRef<HTMLDivElement | null>(null)

  const normalizedEquity = useMemo(() => normalizeEquity(equityCurve), [equityCurve])

  const drawdownSeries = useMemo(() => computeDrawdownSeries(normalizedEquity), [normalizedEquity])
  const latestEquity = normalizedEquity.at(-1)?.value ?? 0
  const maxDrawdown = Math.abs(Math.min(0, ...drawdownSeries.map((p) => p.value)))

  useEffect(() => {
    if (!equityRef.current || normalizedEquity.length === 0) return
    ensureResizeObserver()

    const chart = createChart(equityRef.current, {
      ...CHART_BASE_OPTIONS,
      width: equityRef.current.clientWidth,
      height: 160,
    })

    const series = chart.addSeries(LineSeries, { color: SERIES_COLORS.equity, lineWidth: 2 })
    series.setData(toLineData(normalizedEquity))
    chart.timeScale().fitContent()

    return () => chart.remove()
  }, [normalizedEquity])

  useEffect(() => {
    if (!drawdownRef.current || drawdownSeries.length === 0) return
    ensureResizeObserver()

    const chart = createChart(drawdownRef.current, {
      ...CHART_BASE_OPTIONS,
      width: drawdownRef.current.clientWidth,
      height: 120,
    })

    const series = chart.addSeries(LineSeries, { color: SERIES_COLORS.drawdown, lineWidth: 2 })
    series.setData(toLineData(drawdownSeries))
    chart.timeScale().fitContent()

    return () => chart.remove()
  }, [drawdownSeries])

  if (normalizedEquity.length === 0) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900 p-3 text-xs text-gray-400">
        No performance data available yet.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-[11px] text-gray-400">
        <span>Final equity</span>
        <span className="text-gray-100">${latestEquity.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
      </div>
      <div ref={equityRef} className="h-40 w-full rounded border border-gray-800 bg-gray-900" />

      <div className="flex items-center justify-between text-[11px] text-gray-400">
        <span>Max drawdown</span>
        <span className="text-red-400">-{maxDrawdown.toFixed(2)}%</span>
      </div>
      <div ref={drawdownRef} className="h-32 w-full rounded border border-gray-800 bg-gray-900" />
    </div>
  )
}
