/**
 * TimesFM Forecast Panel
 * ======================
 *
 * Frontend for the TimesFM forecasting lane:
 * - symbol / timeframe / horizon controls -> POST /api/forecast
 * - status line fed by GET /api/forecast/status + the forecast response
 * - chart: historical closes + median (p50) forecast line + p10-p90 band
 *
 * The chart is drawn with the same raw-canvas 2D approach used by
 * EquityCurve.tsx (no chart library dependency in this repo).
 */

import { useEffect, useRef, useState } from 'react'
import {
  getForecastStatus,
  runForecast,
  type ForecastResponse,
  type ForecastStatus,
} from '../api/forecast'
import { useExchangeStore } from '../stores/exchangeStore'

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'] as const

const MIN_HORIZON = 1
const MAX_HORIZON = 256

// Number of historical candles loaded for the chart window.
const HISTORY_CANDLE_LIMIT = 240

type HistoryPoint = {
  t: number
  close: number
}

// Canvas palette (hex is required in canvas; matches the zinc/sky theme).
const HISTORY_COLOR = '#38bdf8' // sky-400
const MEDIAN_COLOR = '#f59e0b' // amber-500
const BAND_FILL = 'rgba(245, 158, 11, 0.16)'
const GRID_COLOR = 'rgba(113, 113, 122, 0.25)' // zinc-500 translucent
const NOW_LINE_COLOR = 'rgba(113, 113, 122, 0.5)'
const TEXT_COLOR = '#71717a' // zinc-500

function formatPrice(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (abs >= 1) return value.toFixed(2)
  return value.toFixed(6)
}

function formatTimestamp(ms: number, spanMs: number): string {
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (spanMs >= 90 * 24 * 3600_000) return `${d.getFullYear()}-${date}`
  if (spanMs >= 48 * 3600_000) return `${date} ${time}`
  return time
}

/**
 * Draw historical closes + forecast quantiles onto a canvas.
 * Layout mirrors EquityCurve.tsx: fixed padding, 4 grid lines, canvas text.
 */
function drawForecastChart(
  canvas: HTMLCanvasElement,
  history: HistoryPoint[],
  forecast: ForecastResponse['points']
): void {
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const rect = canvas.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)

  const width = rect.width
  const height = rect.height
  const padding = { top: 14, right: 14, bottom: 26, left: 62 }
  const innerWidth = width - padding.left - padding.right
  const innerHeight = height - padding.top - padding.bottom

  ctx.clearRect(0, 0, width, height)

  const forecastTimes = forecast.map((p) => Date.parse(p.ts)).filter(Number.isFinite)
  const xCandidates = [
    ...history.map((h) => h.t),
    ...forecastTimes,
  ]
  const yCandidates = [
    ...history.map((h) => h.close),
    ...forecast.flatMap((p) => [p.p10, p.p90]),
  ].filter((v) => Number.isFinite(v))

  if (xCandidates.length === 0 || yCandidates.length === 0) {
    ctx.fillStyle = TEXT_COLOR
    ctx.font = '13px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('No data yet — run a forecast', width / 2, height / 2)
    return
  }

  const xMin = Math.min(...xCandidates)
  const xMax = Math.max(...xCandidates)
  const xSpan = xMax - xMin || 1

  let yMin = Math.min(...yCandidates)
  let yMax = Math.max(...yCandidates)
  if (yMax - yMin < 1e-9) {
    // Flat series: open a small window around the value so lines stay visible.
    const mid = (yMax + yMin) / 2
    yMin = mid * 0.995 - 0.5
    yMax = mid * 1.005 + 0.5
  } else {
    const pad = (yMax - yMin) * 0.04
    yMin -= pad
    yMax += pad
  }

  const xOf = (t: number) => padding.left + ((t - xMin) / xSpan) * innerWidth
  const yOf = (v: number) => padding.top + (1 - (v - yMin) / (yMax - yMin)) * innerHeight

  // Horizontal grid + y labels
  ctx.strokeStyle = GRID_COLOR
  ctx.lineWidth = 1
  ctx.fillStyle = TEXT_COLOR
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const value = yMax - ((yMax - yMin) * i) / 4
    const y = padding.top + (i * innerHeight) / 4
    ctx.beginPath()
    ctx.moveTo(padding.left, y)
    ctx.lineTo(width - padding.right, y)
    ctx.stroke()
    ctx.fillText(formatPrice(value), padding.left - 6, y + 3)
  }

  // X labels (5 ticks; first/last aligned inward to avoid clipping)
  ctx.textAlign = 'center'
  for (let i = 0; i <= 4; i++) {
    const t = xMin + (xSpan * i) / 4
    const x = xOf(t)
    ctx.textAlign = i === 0 ? 'left' : i === 4 ? 'right' : 'center'
    ctx.fillText(
      formatTimestamp(t, xSpan),
      i === 0 ? padding.left : i === 4 ? width - padding.right : x,
      height - 8
    )
  }

  // "Now" separator between history and forecast
  const lastHistory = history.length ? history[history.length - 1] : null
  if (lastHistory && forecast.length > 0) {
    ctx.strokeStyle = NOW_LINE_COLOR
    ctx.setLineDash([4, 4])
    ctx.beginPath()
    const nowX = xOf(lastHistory.t)
    ctx.moveTo(nowX, padding.top)
    ctx.lineTo(nowX, height - padding.bottom)
    ctx.stroke()
    ctx.setLineDash([])
  }

  // p10-p90 band
  if (forecast.length > 0) {
    ctx.fillStyle = BAND_FILL
    ctx.beginPath()
    forecast.forEach((p, idx) => {
      const x = xOf(Date.parse(p.ts))
      const y = yOf(p.p90)
      if (idx === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    for (let idx = forecast.length - 1; idx >= 0; idx--) {
      const p = forecast[idx]
      ctx.lineTo(xOf(Date.parse(p.ts)), yOf(p.p10))
    }
    ctx.closePath()
    ctx.fill()
  }

  // Historical closes
  if (history.length > 0) {
    ctx.strokeStyle = HISTORY_COLOR
    ctx.lineWidth = 1.5
    ctx.beginPath()
    history.forEach((h, idx) => {
      const x = xOf(h.t)
      const y = yOf(h.close)
      if (idx === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
  }

  // Median (p50) forecast line, anchored on the last historical close
  if (forecast.length > 0) {
    ctx.strokeStyle = MEDIAN_COLOR
    ctx.lineWidth = 2
    ctx.beginPath()
    let started = false
    if (lastHistory) {
      ctx.moveTo(xOf(lastHistory.t), yOf(lastHistory.close))
      started = true
    }
    forecast.forEach((p) => {
      const x = xOf(Date.parse(p.ts))
      const y = yOf(p.p50)
      if (!started) {
        ctx.moveTo(x, y)
        started = true
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()
  }
}

export default function ForecastPanel() {
  const exchange = useExchangeStore((state) => state.selectedExchange)

  const [symbol, setSymbol] = useState('BTCUSD')
  const [timeframe, setTimeframe] = useState<string>('1h')
  const [horizonInput, setHorizonInput] = useState('24')

  const [status, setStatus] = useState<ForecastStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)

  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const [forecast, setForecast] = useState<ForecastResponse | null>(null)
  const [forecastError, setForecastError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Model status (loaded / device / ready)
  useEffect(() => {
    let mounted = true
    getForecastStatus()
      .then((s) => {
        if (!mounted) return
        setStatus(s)
        setStatusError(null)
      })
      .catch((err: unknown) => {
        if (!mounted) return
        setStatusError(err instanceof Error ? err.message : 'Unable to fetch forecast status')
      })
    return () => {
      mounted = false
    }
  }, [])

  // Historical closes for the chart window
  useEffect(() => {
    const trimmed = symbol.trim()
    if (!trimmed) {
      setHistory([])
      setHistoryError('Enter a symbol to load historical closes.')
      return
    }

    let inFlight: AbortController | null = null
    const load = () => {
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setHistoryLoading(true)
      setHistoryError(null)

      const url = `/api/candles?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(
        trimmed
      )}&timeframe=${encodeURIComponent(timeframe)}&limit=${HISTORY_CANDLE_LIMIT}`

      fetch(url, { signal: controller.signal })
        .then(async (resp) => {
          const bodyText = await resp.text()
          if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${bodyText.slice(0, 120)}`)
          let payload: unknown
          try {
            payload = JSON.parse(bodyText) as unknown
          } catch {
            throw new Error('Non-JSON response')
          }
          const candles =
            payload && typeof payload === 'object' && 'candles' in payload
              ? (payload as { candles?: unknown }).candles
              : null
          if (!Array.isArray(candles)) throw new Error('Unexpected response format')

          const rows = candles
            .map((row): HistoryPoint | null => {
              if (!row || typeof row !== 'object') return null
              const r = row as Record<string, unknown>
              const t = Number(r.t ?? r.open_time_ms)
              const close = Number(r.c ?? r.close)
              if (!Number.isFinite(t) || !Number.isFinite(close)) return null
              return { t, close }
            })
            .filter((p): p is HistoryPoint => p !== null)
          rows.sort((a, b) => a.t - b.t)
          setHistory(rows.slice(-HISTORY_CANDLE_LIMIT))
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          setHistoryError(
            `Unable to load ${trimmed} ${timeframe} candles (${
              err instanceof Error ? err.message : 'unknown error'
            })`
          )
          setHistory([])
        })
        .finally(() => {
          setHistoryLoading(false)
        })
    }

    load()
    return () => {
      if (inFlight) inFlight.abort()
    }
  }, [exchange, symbol, timeframe])

  // Redraw the chart when data or the window size changes
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const draw = () => drawForecastChart(canvas, history, forecast?.points ?? [])
    draw()
    window.addEventListener('resize', draw)
    return () => window.removeEventListener('resize', draw)
  }, [history, forecast])

  const handleRun = async () => {
    const trimmed = symbol.trim().toUpperCase()
    if (!trimmed) {
      setForecastError('Symbol is required.')
      return
    }
    const horizon = Math.round(Number(horizonInput))
    if (!Number.isFinite(horizon) || horizon < MIN_HORIZON || horizon > MAX_HORIZON) {
      setForecastError(`Horizon must be a whole number between ${MIN_HORIZON} and ${MAX_HORIZON}.`)
      return
    }

    setRunning(true)
    setForecastError(null)
    try {
      const result = await runForecast(trimmed, timeframe, horizon)
      setForecast(result)
    } catch (err: unknown) {
      setForecast(null)
      setForecastError(err instanceof Error ? err.message : 'Forecast request failed.')
    } finally {
      setRunning(false)
    }
  }

  const generatedLabel = (() => {
    if (!forecast) return null
    const parsed = Date.parse(forecast.generated_at)
    return Number.isNaN(parsed)
      ? forecast.generated_at
      : new Date(parsed).toLocaleString('en-GB')
  })()

  const statusReadyLabel = status
    ? status.ready
      ? 'ready'
      : 'not ready'
    : statusError
      ? 'unavailable'
      : 'checking…'

  return (
    <div className="rounded border border-zinc-700 bg-[var(--panel)] p-4 text-zinc-200">
      {/* Header */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-zinc-200">TimesFM Forecast</h2>
          <p className="text-xs text-zinc-500">
            Quantile forecast (p10 / p50 / p90) over the next N candles
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Symbol
          </span>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="BTCUSD"
            spellCheck={false}
            className="w-28 rounded border border-zinc-700 bg-[var(--panel-2)] px-2 py-1 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Timeframe
          </span>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="rounded border border-zinc-700 bg-[var(--panel-2)] px-2 py-1 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Horizon (candles)
          </span>
          <input
            type="number"
            min={MIN_HORIZON}
            max={MAX_HORIZON}
            value={horizonInput}
            onChange={(e) => setHorizonInput(e.target.value)}
            className="w-24 rounded border border-zinc-700 bg-[var(--panel-2)] px-2 py-1 text-sm text-zinc-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </label>

        <button
          type="button"
          onClick={handleRun}
          disabled={running}
          className="rounded bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? 'Running…' : 'Run forecast'}
        </button>
      </div>

      {/* Status line */}
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-400">
        <span>
          Model: <span className="text-zinc-200">{status?.model_id ?? '—'}</span>
        </span>
        <span>
          Device: <span className="text-zinc-200">{status?.device ?? '—'}</span>
        </span>
        <span>
          Status:{' '}
          <span
            className={
              status
                ? status.ready
                  ? 'text-green-400'
                  : 'text-yellow-400'
                : 'text-zinc-500'
            }
          >
            {statusReadyLabel}
          </span>
        </span>
        {forecast && (
          <>
            <span>
              Cache:{' '}
              <span
                className={
                  forecast.cache === 'hit' ? 'text-green-400' : 'text-zinc-200'
                }
              >
                {forecast.cache.toUpperCase()}
              </span>
            </span>
            <span>
              Latency: <span className="text-zinc-200">{forecast.latency_ms} ms</span>
            </span>
            <span>
              Generated: <span className="text-zinc-200">{generatedLabel ?? '—'}</span>
            </span>
          </>
        )}
        {running && <span className="text-sky-400">Generating forecast…</span>}
      </div>

      {/* Errors */}
      {statusError && (
        <div
          role="alert"
          className="mb-3 rounded border border-zinc-700 bg-[var(--panel-2)] p-2 text-xs text-yellow-400"
        >
          Forecast status unavailable: {statusError}
        </div>
      )}
      {historyError && (
        <div
          role="alert"
          className="mb-3 rounded border border-zinc-700 bg-[var(--panel-2)] p-2 text-xs text-yellow-400"
        >
          {historyError}
        </div>
      )}
      {forecastError && (
        <div
          role="alert"
          className="mb-3 rounded border border-red-700 bg-red-900/30 p-2 text-xs text-red-400"
        >
          {forecastError}
        </div>
      )}

      {/* Legend */}
      <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ background: HISTORY_COLOR }} />
          History ({exchange})
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ background: MEDIAN_COLOR }} />
          p50 median
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: BAND_FILL }} />
          p10–p90 band
        </span>
        {historyLoading && <span className="text-zinc-400">Loading history…</span>}
      </div>

      {/* Chart */}
      <div className="rounded border border-zinc-800 bg-[var(--panel-2)] p-1">
        <canvas ref={canvasRef} className="block w-full" style={{ height: '320px' }} />
      </div>

      <p className="mt-2 text-[11px] text-zinc-500">
        Last {history.length} closes shown · forecast starts at the next {timeframe} candle
        after the latest close.
      </p>
    </div>
  )
}
