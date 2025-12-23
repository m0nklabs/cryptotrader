import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

type Theme = 'light' | 'dark'

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const saved = window.localStorage.getItem('theme')
  if (saved === 'light' || saved === 'dark') return saved
  return 'dark'
}

function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

type PanelProps = {
  title: string
  subtitle?: string
  children?: ReactNode
}

function Panel({ title, subtitle, children }: PanelProps) {
  return (
    <details open className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900">
      <summary className="cursor-pointer select-none list-none">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-semibold tracking-wide text-gray-900 dark:text-gray-100">{title}</div>
            {subtitle ? <div className="text-xs text-gray-600 dark:text-gray-400">{subtitle}</div> : null}
          </div>
          <div className="shrink-0 select-none text-xs text-gray-500 dark:text-gray-400">
            <span className="ct-caret inline-block">^</span>
          </div>
        </div>
      </summary>
      <div className="mt-2 text-sm text-gray-800 dark:text-gray-200">{children}</div>
    </details>
  )
}

function Kvp({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-600 dark:text-gray-400">{k}</span>
      <span className="text-xs">{v}</span>
    </div>
  )
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => getInitialTheme())
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsRef = useRef<HTMLDivElement | null>(null)

  const [chartSymbol, setChartSymbol] = useState<string>('BTCUSD')
  const [chartTimeframe, setChartTimeframe] = useState<string>('1m')
  const [chartLimit, setChartLimit] = useState<number>(480)
  const [chartCandles, setChartCandles] = useState<
    Array<{ t: number; o: number; h: number; l: number; c: number; v: number }>
  >([])
  const [chartError, setChartError] = useState<string | null>(null)
  const [chartLoading, setChartLoading] = useState(false)

  const [availableSymbols, setAvailableSymbols] = useState<string[]>([])
  const [availableTimeframesBySymbol, setAvailableTimeframesBySymbol] = useState<Record<string, string[]>>({})
  const [availableError, setAvailableError] = useState<string | null>(null)

  const marketCapRank: Record<string, number> = {
    BTC: 1,
    ETH: 2,
    XRP: 3,
    SOL: 4,
    ADA: 5,
    DOGE: 6,
    LTC: 7,
    AVAX: 8,
    LINK: 9,
    DOT: 10,
  }

  const baseAssetOf = (symbol: string) => {
    const s = symbol.toUpperCase().trim()
    if (s.endsWith('USD') && s.length > 3) return s.slice(0, -3)
    return s
  }

  const sortSymbolsByMarketCap = (symbols: string[]) => {
    const sorted = [...symbols]
    sorted.sort((a, b) => {
      const ar = marketCapRank[baseAssetOf(a)] ?? Number.POSITIVE_INFINITY
      const br = marketCapRank[baseAssetOf(b)] ?? Number.POSITIVE_INFINITY
      if (ar !== br) return ar - br
      return a.localeCompare(b)
    })
    return sorted
  }

  const pickDefaultTimeframe = (timeframes: string[]) => {
    if (timeframes.includes('1m')) return '1m'
    if (timeframes.includes('5m')) return '5m'
    if (timeframes.includes('15m')) return '15m'
    if (timeframes.includes('1h')) return '1h'
    if (timeframes.includes('4h')) return '4h'
    if (timeframes.includes('1d')) return '1d'
    return timeframes[0] || '1m'
  }

  useEffect(() => {
    applyTheme(theme)
    window.localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    const controller = new AbortController()
    setAvailableError(null)

    fetch(`/api/candles/available?exchange=${encodeURIComponent('bitfinex')}`, { signal: controller.signal })
      .then(async (resp) => {
        const bodyText = await resp.text()
        if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${bodyText.slice(0, 120)}`)

        let payload: unknown
        try {
          payload = JSON.parse(bodyText) as unknown
        } catch {
          throw new Error(`Non-JSON response: ${bodyText.slice(0, 120)}`)
        }

        const pairs =
          payload && typeof payload === 'object' && 'pairs' in payload
            ? (payload as { pairs?: unknown }).pairs
            : null
        if (!Array.isArray(pairs)) throw new Error('Unexpected response format')

        const tfBySym: Record<string, Set<string>> = {}
        for (const p of pairs) {
          if (!p || typeof p !== 'object') continue
          const sym = String((p as { symbol?: unknown }).symbol || '').toUpperCase()
          const tf = String((p as { timeframe?: unknown }).timeframe || '')
          if (!sym || !tf) continue
          if (!tfBySym[sym]) tfBySym[sym] = new Set<string>()
          tfBySym[sym].add(tf)
        }

        const normalized: Record<string, string[]> = {}
        for (const [sym, tfs] of Object.entries(tfBySym)) {
          normalized[sym] = Array.from(tfs).sort()
        }

        const symbols = sortSymbolsByMarketCap(Object.keys(normalized))

        setAvailableTimeframesBySymbol(normalized)
        setAvailableSymbols(symbols)

        if (!symbols.length) return

        const selectedSymbol = symbols.includes(chartSymbol) ? chartSymbol : symbols[0]
        if (selectedSymbol !== chartSymbol) setChartSymbol(selectedSymbol)

        const timeframes = normalized[selectedSymbol] || []
        if (timeframes.length && !timeframes.includes(chartTimeframe)) {
          setChartTimeframe(pickDefaultTimeframe(timeframes))
        }
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        const message = err instanceof Error ? err.message : 'Unknown error'
        setAvailableError(`Unable to load available symbols (${message})`)
        setAvailableSymbols([])
        setAvailableTimeframesBySymbol({})
      })

    return () => controller.abort()
  }, [])

  const timeframesForChartSymbol = useMemo(() => {
    const tfs = availableTimeframesBySymbol[chartSymbol]
    if (tfs && tfs.length) return tfs
    return ['1m']
  }, [availableTimeframesBySymbol, chartSymbol])

  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const exchange = 'bitfinex'
    const timeframe = chartTimeframe

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setChartLoading(true)
      setChartError(null)

      const url = `/api/candles?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(
        chartSymbol,
      )}&timeframe=${encodeURIComponent(timeframe)}&limit=${encodeURIComponent(String(chartLimit))}`

      fetch(url, { signal: controller.signal })
        .then(async (resp) => {
          const bodyText = await resp.text()
          if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}: ${bodyText.slice(0, 120)}`)
          }

          let payload: unknown
          try {
            payload = JSON.parse(bodyText) as unknown
          } catch {
            throw new Error(`Non-JSON response: ${bodyText.slice(0, 120)}`)
          }

          const candles =
            payload && typeof payload === 'object' && 'candles' in payload
              ? (payload as { candles?: unknown }).candles
              : null
          if (!Array.isArray(candles)) throw new Error('Unexpected response format')

          const rows = candles
            .map((row) => {
              if (!row || typeof row !== 'object') return null
              const t = Number((row as { t?: unknown }).t)
              const o = Number((row as { o?: unknown }).o)
              const h = Number((row as { h?: unknown }).h)
              const l = Number((row as { l?: unknown }).l)
              const c = Number((row as { c?: unknown }).c)
              const v = Number((row as { v?: unknown }).v)
              if (![t, o, h, l, c, v].every(Number.isFinite)) return null
              return { t, o, h, l, c, v }
            })
            .filter(
              (r): r is { t: number; o: number; h: number; l: number; c: number; v: number } => r !== null,
            )

          setChartCandles(rows)
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          const message = err instanceof Error ? err.message : 'Unknown error'
          setChartError(`Unable to load ${chartSymbol} ${timeframe} candles from DB (${message})`)
          setChartCandles([])
        })
        .finally(() => {
          setChartLoading(false)
        })
    }

    load()
    const id = window.setInterval(load, 15_000)

    return () => {
      mounted = false
      window.clearInterval(id)
      if (inFlight) inFlight.abort()
    }
  }, [chartSymbol, chartTimeframe, chartLimit])

  const onChartWheel = (ev: React.WheelEvent<HTMLDivElement>) => {
    // Wheel zoom: scroll up -> zoom in (fewer candles), scroll down -> zoom out (more candles).
    // Keep it simple: adjust the fetched window size.
    ev.preventDefault()

    const direction = ev.deltaY > 0 ? 1 : -1
    setChartLimit((prev) => {
      const min = 60
      const max = 2000
      const next = Math.round(prev * (direction > 0 ? 1.25 : 0.8))
      return Math.max(min, Math.min(max, next))
    })
  }

  const btcusdChart = useMemo(() => {
    if (!chartCandles.length) return null

    const width = 720
    const height = 320
    const paddingX = 10
    const paddingY = 12
    const volumeHeight = 70
    const priceHeight = height - volumeHeight

    const lows = chartCandles.map((c) => c.l)
    const highs = chartCandles.map((c) => c.h)
    const min = Math.min(...lows)
    const max = Math.max(...highs)
    const range = max - min
    const safeRange = range === 0 ? 1 : range

    const volumes = chartCandles.map((c) => c.v)
    const volMax = Math.max(1, ...volumes)

    const x0 = paddingX
    const x1 = width - paddingX
    const y0 = paddingY
    const y1 = priceHeight - paddingY

    const toX = (i: number) => x0 + ((i + 0.5) / chartCandles.length) * (x1 - x0)
    const toY = (value: number) => y1 - ((value - min) / safeRange) * (y1 - y0)

    const candleSpan = (x1 - x0) / Math.max(1, chartCandles.length)
    const candleW = Math.max(1, candleSpan * 0.7)

    const last = chartCandles[chartCandles.length - 1]
    const lastTs = new Date(last.t).toISOString().slice(0, 16).replace('T', ' ')

    return {
      width,
      height,
      priceHeight,
      volumeHeight,
      x0,
      x1,
      candleW,
      toX,
      toY,
      volMax,
      lastClose: last.c,
      lastTs,
      candles: chartCandles,
    }
  }, [chartCandles])

  useEffect(() => {
    if (!settingsOpen) return

    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setSettingsOpen(false)
    }

    const onMouseDown = (ev: MouseEvent) => {
      const el = settingsRef.current
      if (!el) return
      if (ev.target instanceof Node && !el.contains(ev.target)) {
        setSettingsOpen(false)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('mousedown', onMouseDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('mousedown', onMouseDown)
    }
  }, [settingsOpen])

  const nextThemeLabel = useMemo(() => (theme === 'dark' ? 'light' : 'dark'), [theme])

  return (
    <div className="min-h-screen bg-gray-50 text-sm text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-10 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-3 py-2">
            <div className="text-sm font-semibold">cryptotrader</div>
            <div className="flex items-center gap-3">
              <div className="text-xs text-gray-600 dark:text-gray-400">dashboard</div>

              <div ref={settingsRef} className="relative">
                <button
                  type="button"
                  aria-label="Settings"
                  className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                  onClick={() => setSettingsOpen(!settingsOpen)}
                >
                  ⚙
                </button>

                {settingsOpen ? (
                  <div className="absolute right-0 mt-2 w-56 rounded-md border border-gray-200 bg-white p-2 text-xs text-gray-700 shadow-sm dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="font-semibold">Settings</div>
                      <button
                        type="button"
                        className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                        onClick={() => setSettingsOpen(false)}
                      >
                        x
                      </button>
                    </div>

                    <div className="flex items-center justify-between gap-2 rounded border border-gray-200 bg-white px-2 py-2 dark:border-gray-800 dark:bg-gray-900">
                      <span className="text-gray-600 dark:text-gray-400">Theme</span>
                      <button
                        type="button"
                        className="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200 dark:hover:bg-gray-900"
                        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                      >
                        {nextThemeLabel}
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-3 py-3">
          <div className="ct-dock-grid gap-3">
            <div className="ct-dock-left flex flex-col gap-3">
              <Panel title="Market Watch" subtitle="Symbols / tickers">
                <Kvp k="Primary" v="BTCUSD" />
                <div className="mt-2 space-y-1">
                  {availableError ? (
                    <div className="text-xs text-gray-600 dark:text-gray-400">{availableError}</div>
                  ) : availableSymbols.length ? (
                    availableSymbols.map((s) => (
                      <button
                        key={s}
                        type="button"
                        className="flex w-full items-center justify-between rounded px-1 py-0.5 text-xs hover:bg-gray-50 dark:hover:bg-gray-800"
                        onClick={() => {
                          setChartSymbol(s)
                          const tfs = availableTimeframesBySymbol[s]
                          if (tfs && tfs.length && !tfs.includes(chartTimeframe)) {
                            setChartTimeframe(pickDefaultTimeframe(tfs))
                          }
                        }}
                      >
                        <span className="text-gray-600 dark:text-gray-400">{s}</span>
                        <span className={s === chartSymbol ? 'text-gray-900 dark:text-gray-100' : ''}>
                          {s === chartSymbol ? '•' : '—'}
                        </span>
                      </button>
                    ))
                  ) : (
                    <div className="text-xs text-gray-600 dark:text-gray-400">No symbols in DB.</div>
                  )}
                </div>
              </Panel>

              <Panel title="Market Data" subtitle="Bitfinex candles (OHLCV)">
                <Kvp k="Status" v="Not connected" />
                <div className="mt-2">
                  <Kvp k="Latest run" v="—" />
                </div>
              </Panel>
            </div>

            <div className="ct-dock-center flex flex-col gap-3">
              <Panel title="Chart" subtitle="Price + volume">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="truncate">{chartSymbol}</span>
                      <select
                        className="rounded border border-gray-200 bg-white px-1 py-0.5 text-xs text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-200"
                        value={chartTimeframe}
                        onChange={(ev) => setChartTimeframe(ev.target.value)}
                      >
                        {timeframesForChartSymbol.map((tf) => (
                          <option key={tf} value={tf}>
                            {tf}
                          </option>
                        ))}
                      </select>
                      <span className="whitespace-nowrap">(DB candles, window: {chartLimit})</span>
                    </div>
                    {btcusdChart ? (
                      <span>
                        last: <span className="text-gray-900 dark:text-gray-100">{btcusdChart.lastClose.toFixed(2)}</span> @ {btcusdChart.lastTs}
                      </span>
                    ) : null}
                  </div>

                  <div
                    className="rounded border border-gray-200 bg-white p-2 dark:border-gray-800 dark:bg-gray-900"
                    onWheel={onChartWheel}
                  >
                    {chartLoading ? (
                      <div className="text-xs text-gray-600 dark:text-gray-400">Loading candles…</div>
                    ) : chartError ? (
                      <div className="text-xs text-gray-600 dark:text-gray-400">{chartError}</div>
                    ) : btcusdChart ? (
                      <svg viewBox={`0 0 ${btcusdChart.width} ${btcusdChart.height}`} className="h-72 w-full">
                        <rect
                          x={0}
                          y={0}
                          width={btcusdChart.width}
                          height={btcusdChart.height}
                          className="fill-gray-50 dark:fill-gray-950"
                        />

                        {/* Price candlesticks */}
                        {btcusdChart.candles.map((c, i) => {
                          const x = btcusdChart.toX(i)
                          const yHigh = btcusdChart.toY(c.h)
                          const yLow = btcusdChart.toY(c.l)
                          const yOpen = btcusdChart.toY(c.o)
                          const yClose = btcusdChart.toY(c.c)
                          const up = c.c >= c.o
                          const bodyY = Math.min(yOpen, yClose)
                          const bodyH = Math.max(1, Math.abs(yClose - yOpen))

                          const wickClass = up
                            ? 'stroke-gray-900 dark:stroke-gray-100'
                            : 'stroke-gray-500 dark:stroke-gray-400'
                          const bodyClass = up
                            ? 'fill-gray-900 dark:fill-gray-100'
                            : 'fill-gray-500 dark:fill-gray-400'

                          return (
                            <g key={c.t}>
                              <line x1={x} y1={yHigh} x2={x} y2={yLow} className={wickClass} strokeWidth={1} />
                              <rect
                                x={x - btcusdChart.candleW / 2}
                                y={bodyY}
                                width={btcusdChart.candleW}
                                height={bodyH}
                                className={bodyClass}
                              />
                            </g>
                          )
                        })}

                        {/* Volume bars */}
                        {btcusdChart.candles.map((c, i) => {
                          const x = btcusdChart.toX(i)
                          const up = c.c >= c.o
                          const barMaxH = btcusdChart.volumeHeight - 10
                          const barH = Math.max(1, (c.v / btcusdChart.volMax) * barMaxH)
                          const y = btcusdChart.priceHeight + (btcusdChart.volumeHeight - barH) - 4
                          const barClass = up
                            ? 'fill-gray-700 dark:fill-gray-300'
                            : 'fill-gray-400 dark:fill-gray-600'

                          return (
                            <rect
                              key={`v-${c.t}`}
                              x={x - btcusdChart.candleW / 2}
                              y={y}
                              width={btcusdChart.candleW}
                              height={barH}
                              className={barClass}
                            />
                          )
                        })}
                      </svg>
                    ) : (
                      <div className="text-xs text-gray-600 dark:text-gray-400">No candle data.</div>
                    )}
                  </div>
                </div>
              </Panel>

              <div className="ct-dock-bottom flex flex-col gap-3">
                <Panel title="Terminal" subtitle="Orders / positions / logs">
                  <Kvp k="Orders" v="0" />
                  <div className="mt-2">
                    <Kvp k="Positions" v="0" />
                  </div>
                  <div className="mt-2 rounded border border-gray-200 bg-white p-2 text-[11px] text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
                    <div className="font-mono">[log] service online</div>
                    <div className="font-mono">[log] waiting for backend</div>
                  </div>
                </Panel>
              </div>
            </div>

            <div className="ct-dock-right flex flex-col gap-3">
              <Panel title="Opportunities" subtitle="Signals snapshot">
                <Kvp k="Top symbol" v="—" />
                <div className="mt-2">
                  <Kvp k="Score" v="—" />
                </div>
              </Panel>

              <Panel title="Data Quality" subtitle="Candle gaps">
                <Kvp k="Open gaps" v="—" />
                <div className="mt-2">
                  <Kvp k="Last repair" v="—" />
                </div>
              </Panel>

              <Panel title="Execution" subtitle="Intents / results">
                <Kvp k="Mode" v="dry-run" />
                <div className="mt-2">
                  <Kvp k="Last order" v="—" />
                </div>
              </Panel>

              <Panel title="System" subtitle="Health">
                <Kvp k="Backend" v="—" />
                <div className="mt-2">
                  <Kvp k="Database" v="—" />
                </div>
              </Panel>
            </div>
          </div>
        </main>

        <footer className="sticky bottom-0 border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
            <span>v2 skeleton</span>
            <span>paper-trading default</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
