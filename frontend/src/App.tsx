import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import CandlestickChart from './components/CandlestickChart'
import OrderForm from './components/OrderForm'
import OrdersTable from './components/OrdersTable'
import PositionsTable from './components/PositionsTable'
import {
  placeOrder,
  listOrders,
  cancelOrder,
  listPositions,
  closePosition,
  type Order,
  type Position,
  type PlaceOrderRequest,
} from './api/trading'
import { fetchMarketCap } from './api/marketCap'

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

const GAP_STATS_REFRESH_INTERVAL_MS = 60_000
const SIGNALS_REFRESH_INTERVAL_MS = 30_000
const INGESTION_STATUS_REFRESH_INTERVAL_MS = 15_000
const WALLET_REFRESH_INTERVAL_MS = 30_000
const MARKET_CAP_REFRESH_INTERVAL_MS = 600_000 // 10 minutes

type Signal = {
  symbol: string
  timeframe: string
  score: number
  side: string
  signals: Array<{
    code: string
    side: string
    strength: number
    value: string
    reason: string
  }>
  created_at: number
}

type Wallet = {
  type: string
  currency: string
  balance: number
  available: number
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

  const [gapStats, setGapStats] = useState<{
    open_gaps: number
    repaired_24h: number
    oldest_open_gap: number | null
  } | null>(null)
  const [gapStatsError, setGapStatsError] = useState<string | null>(null)

  const [signals, setSignals] = useState<Signal[]>([])
  const [signalsError, setSignalsError] = useState<string | null>(null)

  const [wallets, setWallets] = useState<Wallet[]>([])
  const [walletsError, setWalletsError] = useState<string | null>(null)
  const [walletsLoading, setWalletsLoading] = useState(false)

  const [ingestionStatus, setIngestionStatus] = useState<{
    apiReachable: boolean
    btcusd1mLatestTime: number | null
    gapStats: {
      open_gaps: number
      repaired_24h: number
      oldest_open_gap: number | null
    } | null
  }>({
    apiReachable: false,
    btcusd1mLatestTime: null,
    gapStats: null,
  })
  const [ingestionStatusError, setIngestionStatusError] = useState<string | null>(null)

  // Paper trading state
  const [orders, setOrders] = useState<Order[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [tradingLoading, setTradingLoading] = useState(false)

  // Market cap rankings state
  const [marketCapRank, setMarketCapRank] = useState<Record<string, number>>({
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
  })
  const [marketCapSource, setMarketCapSource] = useState<'coingecko' | 'fallback'>('fallback')

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

  const formatCurrency = (amount: number, currency: string): string => {
    const decimals = currency === 'USD' || currency === 'USDT' ? 2 : 8
    return amount.toFixed(decimals)
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

  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setGapStatsError(null)

      fetch('/api/gaps/summary', { signal: controller.signal })
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

          if (!payload || typeof payload !== 'object') {
            throw new Error('Unexpected response format')
          }

          const stats = payload as { open_gaps?: unknown; repaired_24h?: unknown; oldest_open_gap?: unknown }
          const openGaps = Number(stats.open_gaps)
          const repaired24h = Number(stats.repaired_24h)
          const oldestGap = stats.oldest_open_gap === null ? null : Number(stats.oldest_open_gap)

          if (!Number.isFinite(openGaps) || !Number.isFinite(repaired24h)) {
            throw new Error('Invalid gap stats format')
          }

          setGapStats({
            open_gaps: openGaps,
            repaired_24h: repaired24h,
            oldest_open_gap: oldestGap,
          })
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          const message = err instanceof Error ? err.message : 'Unknown error'
          setGapStatsError(`Unable to load gap stats (${message})`)
          setGapStats(null)
        })
    }

    load()
    const id = window.setInterval(load, GAP_STATS_REFRESH_INTERVAL_MS)

    return () => {
      mounted = false
      window.clearInterval(id)
      if (inFlight) inFlight.abort()
    }
  }, [])

  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setSignalsError(null)

      fetch('/api/signals?exchange=bitfinex&limit=10', { signal: controller.signal })
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

          if (!payload || typeof payload !== 'object') {
            throw new Error('Unexpected response format')
          }

          const signalsData =
            payload && typeof payload === 'object' && 'signals' in payload
              ? (payload as { signals?: unknown }).signals
              : null
          if (!Array.isArray(signalsData)) throw new Error('Unexpected response format')

          const parsed: Signal[] = signalsData
            .map((sig) => {
              if (!sig || typeof sig !== 'object') return null
              const s = sig as Record<string, unknown>
              return {
                symbol: String(s.symbol || ''),
                timeframe: String(s.timeframe || ''),
                score: Number(s.score || 0),
                side: String(s.side || 'HOLD'),
                signals: Array.isArray(s.signals) ? s.signals : [],
                created_at: Number(s.created_at || 0),
              }
            })
            .filter((s): s is Signal => s !== null)

          setSignals(parsed)
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          const message = err instanceof Error ? err.message : 'Unknown error'
          setSignalsError(`Unable to load signals (${message})`)
          setSignals([])
        })
    }

    load()
    const id = window.setInterval(load, SIGNALS_REFRESH_INTERVAL_MS)

    return () => {
      mounted = false
      window.clearInterval(id)
      if (inFlight) inFlight.abort()
    }
  }, [])

  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setWalletsLoading(true)
      setWalletsError(null)

      fetch('/api/wallet/balances', { signal: controller.signal })
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

          if (!payload || typeof payload !== 'object') {
            throw new Error('Unexpected response format')
          }

          const walletsData =
            payload && typeof payload === 'object' && 'wallets' in payload
              ? (payload as { wallets?: unknown }).wallets
              : null
          if (!Array.isArray(walletsData)) throw new Error('Unexpected response format')

          const parsed: Wallet[] = walletsData
            .map((w) => {
              if (!w || typeof w !== 'object') return null
              const wallet = w as Record<string, unknown>
              return {
                type: String(wallet.type || ''),
                currency: String(wallet.currency || ''),
                balance: Number(wallet.balance || 0),
                available: Number(wallet.available || 0),
              }
            })
            .filter((w): w is Wallet => w !== null)

          setWallets(parsed)
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          const message = err instanceof Error ? err.message : 'Unknown error'
          setWalletsError(`Unable to load wallet balances (${message})`)
          setWallets([])
        })
        .finally(() => {
          setWalletsLoading(false)
        })
    }

    load()
    const id = window.setInterval(load, WALLET_REFRESH_INTERVAL_MS)

    return () => {
      mounted = false
      window.clearInterval(id)
      if (inFlight) inFlight.abort()
    }
  }, [])

  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setIngestionStatusError(null)

      const fallbackToLegacy = async (): Promise<{ apiReachable: boolean; latestTime: number | null }> => {
        const resp = await fetch('/api/ingestion/status?exchange=bitfinex&symbol=BTCUSD&timeframe=1m', {
          signal: controller.signal,
        })
        const bodyText = await resp.text()
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

        let payload: unknown
        try {
          payload = JSON.parse(bodyText) as unknown
        } catch {
          throw new Error('Non-JSON response')
        }

        if (!payload || typeof payload !== 'object') throw new Error('Unexpected response format')

        const data = payload as { api_reachable?: unknown; latest_candle_time?: unknown }
        return {
          apiReachable: data.api_reachable === true,
          latestTime: typeof data.latest_candle_time === 'number' ? data.latest_candle_time : null,
        }
      }

      const healthCheck = async (): Promise<boolean> => {
        try {
          const resp = await fetch('/health', { signal: controller.signal })
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
          return true
        } catch {
          const resp = await fetch('/healthz', { signal: controller.signal })
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
          return true
        }
      }

      const fastApiIngestion = async (): Promise<number | null> => {
        const resp = await fetch('/ingestion/status?exchange=bitfinex&symbol=BTCUSD&timeframe=1m', {
          signal: controller.signal,
        })
        const bodyText = await resp.text()
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

        let payload: unknown
        try {
          payload = JSON.parse(bodyText) as unknown
        } catch {
          throw new Error('Non-JSON response')
        }

        if (!payload || typeof payload !== 'object') throw new Error('Unexpected response format')

        const data = payload as { latest_candle_open_time?: unknown }
        return typeof data.latest_candle_open_time === 'number' ? data.latest_candle_open_time : null
      }

      Promise.all([healthCheck(), fastApiIngestion()])
        .then(([apiReachable, latestTime]) => {
          setIngestionStatus({
            apiReachable,
            btcusd1mLatestTime: latestTime,
            gapStats: gapStats,
          })
        })
        .catch(() => {
          return fallbackToLegacy().then(({ apiReachable, latestTime }) => {
            setIngestionStatus({
              apiReachable,
              btcusd1mLatestTime: latestTime,
              gapStats: gapStats,
            })
          })
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          const message = err instanceof Error ? err.message : 'Unknown error'
          setIngestionStatusError(`API check failed (${message})`)
          setIngestionStatus({
            apiReachable: false,
            btcusd1mLatestTime: null,
            gapStats: gapStats,
          })
        })
    }

    load()
    const id = window.setInterval(load, INGESTION_STATUS_REFRESH_INTERVAL_MS)

    return () => {
      mounted = false
      window.clearInterval(id)
      if (inFlight) inFlight.abort()
    }
  }, [gapStats])

  // Fetch market cap rankings
  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      fetchMarketCap(controller.signal)
        .then((data) => {
          if (!mounted) return
          setMarketCapRank(data.rankings)
          setMarketCapSource(data.source)
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          console.warn('Failed to fetch market cap rankings, using fallback:', err)
          // Keep existing fallback rankings on error
        })
    }

    load()
    const id = window.setInterval(load, MARKET_CAP_REFRESH_INTERVAL_MS)

    return () => {
      mounted = false
      window.clearInterval(id)
      if (inFlight) inFlight.abort()
    }
  }, [])

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

  // Paper trading: fetch orders and positions
  const TRADING_REFRESH_INTERVAL_MS = 5_000

  const fetchTradingData = useCallback(async () => {
    try {
      const [ordersData, positionsData] = await Promise.all([
        listOrders(),
        listPositions(),
      ])
      setOrders(ordersData)
      setPositions(positionsData)
    } catch (err) {
      console.error('Failed to fetch trading data:', err)
    }
  }, [])

  useEffect(() => {
    fetchTradingData()
    const interval = setInterval(fetchTradingData, TRADING_REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchTradingData])

  const handlePlaceOrder = useCallback(
    async (request: PlaceOrderRequest) => {
      setTradingLoading(true)
      try {
        await placeOrder(request)
        await fetchTradingData()
      } finally {
        setTradingLoading(false)
      }
    },
    [fetchTradingData]
  )

  const handleCancelOrder = useCallback(
    async (orderId: number) => {
      setTradingLoading(true)
      try {
        await cancelOrder(orderId)
        await fetchTradingData()
      } finally {
        setTradingLoading(false)
      }
    },
    [fetchTradingData]
  )

  const handleClosePosition = useCallback(
    async (symbol: string) => {
      // Get current price from chart data
      const lastCandle = chartCandles[chartCandles.length - 1]
      if (!lastCandle) {
        console.error('No price data available')
        return
      }
      setTradingLoading(true)
      try {
        await closePosition(symbol, lastCandle.c.toString())
        await fetchTradingData()
      } finally {
        setTradingLoading(false)
      }
    },
    [fetchTradingData, chartCandles]
  )

  // Get current price for order form
  const currentPrice = useMemo(() => {
    const lastCandle = chartCandles[chartCandles.length - 1]
    return lastCandle?.c
  }, [chartCandles])

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
              <Panel 
                title="Market Watch" 
                subtitle={`Symbols / tickers${marketCapSource === 'coingecko' ? ' (live rankings)' : ''}`}
              >
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
                {ingestionStatusError ? (
                  <div className="text-xs text-gray-600 dark:text-gray-400">{ingestionStatusError}</div>
                ) : (
                  <>
                    <Kvp
                      k="API"
                      v={
                        <span className={ingestionStatus.apiReachable ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                          {ingestionStatus.apiReachable ? 'Reachable' : 'Unreachable'}
                        </span>
                      }
                    />
                    <div className="mt-2">
                      <Kvp
                        k="BTCUSD-1m latest"
                        v={
                          ingestionStatus.btcusd1mLatestTime !== null
                            ? new Date(ingestionStatus.btcusd1mLatestTime).toISOString().slice(0, 16).replace('T', ' ')
                            : '—'
                        }
                      />
                    </div>
                    {ingestionStatus.gapStats && (
                      <div className="mt-2">
                        <Kvp
                          k="Open gaps"
                          v={
                            <span className={ingestionStatus.gapStats.open_gaps > 0 ? 'text-yellow-600 dark:text-yellow-400' : 'text-green-600 dark:text-green-400'}>
                              {ingestionStatus.gapStats.open_gaps}
                            </span>
                          }
                        />
                      </div>
                    )}
                  </>
                )}
              </Panel>

              <Panel title="Wallet" subtitle="Bitfinex balances">
                {walletsLoading && wallets.length === 0 ? (
                  <div className="text-xs text-gray-600 dark:text-gray-400">Loading balances...</div>
                ) : walletsError ? (
                  <div className="text-xs text-gray-600 dark:text-gray-400">{walletsError}</div>
                ) : wallets.length > 0 ? (
                  <>
                    {['exchange', 'margin', 'funding'].map((walletType) => {
                      const typeWallets = wallets.filter((w) => w.type === walletType)
                      if (typeWallets.length === 0) return null

                      return (
                        <div key={walletType} className="mb-2">
                          <div className="mb-1 text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                            {walletType}
                          </div>
                          <div className="space-y-1">
                            {typeWallets.map((w, idx) => {
                              // Only show non-zero balances
                              if (w.balance === 0) return null

                              return (
                                <div
                                  key={`${walletType}-${w.currency}-${idx}`}
                                  className="flex items-center justify-between text-xs"
                                >
                                  <span className="text-gray-600 dark:text-gray-400">{w.currency}</span>
                                  <div className="flex flex-col items-end">
                                    <span className="text-gray-900 dark:text-gray-100">
                                      {formatCurrency(w.balance, w.currency)}
                                    </span>
                                    {w.available !== w.balance && (
                                      <span className="text-[10px] text-gray-500 dark:text-gray-500">
                                        avail: {formatCurrency(w.available, w.currency)}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </>
                ) : (
                  <div className="text-xs text-gray-600 dark:text-gray-400">No balances available</div>
                )}
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
                  </div>

                  <div onWheel={onChartWheel}>
                    {chartLoading ? (
                      <div className="rounded border border-gray-200 bg-white p-2 text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
                        Loading candles…
                      </div>
                    ) : chartError ? (
                      <div className="rounded border border-gray-200 bg-white p-2 text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
                        {chartError}
                      </div>
                    ) : chartCandles.length > 0 ? (
                      <CandlestickChart
                        candles={chartCandles.map((c) => ({
                          time: Math.floor(c.t / 1000),
                          open: c.o,
                          high: c.h,
                          low: c.l,
                          close: c.c,
                          volume: c.v,
                        }))}
                        symbol={chartSymbol}
                        timeframe={chartTimeframe}
                        height={320}
                      />
                    ) : (
                      <div className="rounded border border-gray-200 bg-white p-2 text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
                        No candle data.
                      </div>
                    )}
                  </div>
                </div>
              </Panel>

              <div className="ct-dock-bottom flex flex-col gap-3">
                <Panel title="Orders" subtitle={`${orders.filter(o => o.status === 'PENDING').length} pending / ${orders.filter(o => o.status === 'FILLED').length} filled`}>
                  <OrdersTable
                    orders={orders}
                    onCancel={handleCancelOrder}
                    loading={tradingLoading}
                  />
                </Panel>

                <Panel title="Positions" subtitle={`${positions.filter(p => parseFloat(p.qty) !== 0).length} open`}>
                  <PositionsTable
                    positions={positions}
                    onClose={handleClosePosition}
                    loading={tradingLoading}
                  />
                </Panel>
              </div>
            </div>

            <div className="ct-dock-right flex flex-col gap-3">
              <Panel title="Order Entry" subtitle={chartSymbol}>
                <OrderForm
                  symbol={chartSymbol}
                  currentPrice={currentPrice}
                  onSubmit={handlePlaceOrder}
                  disabled={tradingLoading}
                />
              </Panel>

              <Panel title="Opportunities" subtitle="Signals snapshot">
                {signalsError ? (
                  <div className="text-xs text-gray-600 dark:text-gray-400">{signalsError}</div>
                ) : signals.length > 0 ? (
                  <>
                    <div className="space-y-2">
                      {signals.slice(0, 5).map((sig, idx) => {
                        const sideColor =
                          sig.side === 'BUY'
                            ? 'text-green-600 dark:text-green-400'
                            : sig.side === 'SELL'
                              ? 'text-red-600 dark:text-red-400'
                              : 'text-gray-600 dark:text-gray-400'
                        const scoreColor =
                          sig.score >= 70
                            ? 'text-green-600 dark:text-green-400'
                            : sig.score >= 50
                              ? 'text-yellow-600 dark:text-yellow-400'
                              : 'text-gray-600 dark:text-gray-400'

                        return (
                          <div
                            key={idx}
                            className="rounded border border-gray-200 bg-white p-2 text-xs dark:border-gray-800 dark:bg-gray-900"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-gray-900 dark:text-gray-100">{sig.symbol}</span>
                              <span className={sideColor}>{sig.side}</span>
                            </div>
                            <div className="mt-1 flex items-center justify-between">
                              <span className="text-gray-600 dark:text-gray-400">{sig.timeframe}</span>
                              <span className={scoreColor}>Score: {sig.score}</span>
                            </div>
                            {sig.signals.length > 0 && (
                              <div className="mt-1 space-y-0.5 text-[11px] text-gray-600 dark:text-gray-400">
                                {sig.signals.map((s, i) => (
                                  <div key={i}>• {s.code}: {s.reason}</div>
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </>
                ) : (
                  <>
                    <Kvp k="Top symbol" v="—" />
                    <div className="mt-2">
                      <Kvp k="Score" v="—" />
                    </div>
                  </>
                )}
              </Panel>

              <Panel title="Data Quality" subtitle="Candle gaps">
                {gapStatsError ? (
                  <div className="text-xs text-gray-600 dark:text-gray-400">{gapStatsError}</div>
                ) : gapStats ? (
                  <>
                    <Kvp k="Open gaps" v={gapStats.open_gaps} />
                    <div className="mt-2">
                      <Kvp k="Repaired (24h)" v={gapStats.repaired_24h} />
                    </div>
                    {gapStats.oldest_open_gap !== null ? (
                      <div className="mt-2">
                        <Kvp
                          k="Oldest gap"
                          v={new Date(gapStats.oldest_open_gap).toISOString().slice(0, 16).replace('T', ' ')}
                        />
                      </div>
                    ) : null}
                  </>
                ) : (
                  <>
                    <Kvp k="Open gaps" v="—" />
                    <div className="mt-2">
                      <Kvp k="Repaired (24h)" v="—" />
                    </div>
                  </>
                )}
              </Panel>

              <Panel title="Execution" subtitle="Paper trading">
                <Kvp k="Mode" v="paper" />
                <div className="mt-2">
                  <Kvp k="Total Orders" v={orders.length.toString()} />
                </div>
                <div className="mt-2">
                  <Kvp k="Open Positions" v={positions.filter(p => parseFloat(p.qty) !== 0).length.toString()} />
                </div>
                {orders.length > 0 && (
                  <div className="mt-2">
                    <Kvp
                      k="Last Order"
                      v={`${orders[orders.length - 1].side} ${orders[orders.length - 1].symbol}`}
                    />
                  </div>
                )}
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
