import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import CandlestickChart from './components/CandlestickChart'
import OrderForm from './components/OrderForm'
import OrdersTable from './components/OrdersTable'
import PositionsTable from './components/PositionsTable'
import Sidebar from './components/Sidebar'
import { VIEW_IDS, type ViewId } from './nav'
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
import { createCandleStream, type CandleUpdate } from './api/candleStream'
import { fetchSystemStatus, type SystemStatus } from './api/systemStatus'

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
const SYSTEM_STATUS_REFRESH_INTERVAL_MS = 10_000 // 10 seconds
const MARKET_WATCH_REFRESH_INTERVAL_MS = 30_000 // 30 seconds

type Signal = {
  symbol: string
  timeframe: string
  score: number
  side: string
  price?: number
  change_24h?: number
  rsi?: number
  score_breakdown?: Array<{
    code: string
    contribution: number
    detail?: string
  }>
  score_explanation?: string
  analysis?: {
    recommendation: string
    confidence: number
    score: number
    reasoning: string[]
    bullish_factors: string[]
    bearish_factors: string[]
    support_levels: number[]
    resistance_levels: number[]
    suggested_entry?: number | null
    suggested_stop?: number | null
    suggested_target?: number | null
    risk_reward_ratio?: number | null
    indicators?: {
      rsi?: number
      ema_20?: number
      ema_50?: number
      ema_200?: number
      macd?: number
      atr_percent?: number
      volume_ratio?: number
    }
  }
  llm?: {
    summary?: string
    explanation?: string
    risks?: string
    confidence?: string
    model?: string
  }
  signals: Array<{
    code: string
    side: string
    strength: number
    value: string
    reason: string
  }>
  created_at: number
}

type MarketWatchItem = {
  symbol: string
  price: number
  change_1h: number
  change_24h: number
  high_24h: number
  low_24h: number
  volume_24h: number
  rsi: number | null
  ema_trend: 'bullish' | 'bearish'
  updated_at: number
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activeView, setActiveView] = useState<ViewId>(VIEW_IDS.DASHBOARD)
  const settingsRef = useRef<HTMLDivElement | null>(null)

  const [chartSymbol, setChartSymbol] = useState<string>('BTCUSD')
  const [chartTimeframe, setChartTimeframe] = useState<string>('1h')
  const [chartLimit, setChartLimit] = useState<number>(500)
  const [chartCandles, setChartCandles] = useState<
    Array<{ t: number; o: number; h: number; l: number; c: number; v: number }>
  >([])
  const [chartError, setChartError] = useState<string | null>(null)
  const [chartLoading, setChartLoading] = useState(false)
  const [useWebSocket, setUseWebSocket] = useState(true) // Enable WebSocket by default
  const [wsConnected, setWsConnected] = useState(false)

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

  const [marketWatch, setMarketWatch] = useState<MarketWatchItem[]>([])
  const [marketWatchError, setMarketWatchError] = useState<string | null>(null)

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

  // System status state
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [systemStatusError, setSystemStatusError] = useState<string | null>(null)

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
    // Prefer 1h as practical default (good balance of data + overview)
    // Then higher timeframes, then lower
    if (timeframes.includes('1h')) return '1h'
    if (timeframes.includes('4h')) return '4h'
    if (timeframes.includes('1d')) return '1d'
    if (timeframes.includes('15m')) return '15m'
    if (timeframes.includes('5m')) return '5m'
    if (timeframes.includes('1m')) return '1m'
    return timeframes[0] || '1h'
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
    return ['1h', '4h', '1d', '1m']  // Fallback with reasonable defaults
  }, [availableTimeframesBySymbol, chartSymbol])

  // Real-time candle updates via WebSocket/SSE with polling fallback
  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null
    let candleStream: ReturnType<typeof createCandleStream> | null = null
    let pollInterval: number | null = null

    const exchange = 'bitfinex'
    const timeframe = chartTimeframe

    // Load initial candles from database
    const loadInitialCandles = () => {
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
              // Support both old (t,o,h,l,c,v) and new (open_time_ms,open,high,low,close,volume) formats
              const r = row as Record<string, unknown>
              const t = Number(r.t ?? r.open_time_ms)
              const o = Number(r.o ?? r.open)
              const h = Number(r.h ?? r.high)
              const l = Number(r.l ?? r.low)
              const c = Number(r.c ?? r.close)
              const v = Number(r.v ?? r.volume)
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

    // Update candle with real-time data
    const updateCandle = (candleUpdate: CandleUpdate) => {
      if (!mounted) return

      setChartCandles((prev) => {
        const newCandle = {
          t: candleUpdate.t,
          o: candleUpdate.o,
          h: candleUpdate.h,
          l: candleUpdate.l,
          c: candleUpdate.c,
          v: candleUpdate.v,
        }

        // Find existing candle with same timestamp
        const existingIndex = prev.findIndex((c) => c.t === newCandle.t)

        if (existingIndex >= 0) {
          // Update existing candle
          const updated = [...prev]
          updated[existingIndex] = newCandle
          return updated
        } else {
          // Add new candle
          const updated = [...prev, newCandle]
          // Keep only the most recent candles (limit)
          if (updated.length > chartLimit) {
            return updated.slice(updated.length - chartLimit)
          }
          return updated
        }
      })
    }

    // Setup polling fallback
    const setupPolling = () => {
      if (pollInterval) window.clearInterval(pollInterval)
      // Poll every 15 seconds as fallback
      pollInterval = window.setInterval(loadInitialCandles, 15_000)
    }

    // Start with initial load
    loadInitialCandles()

    // Try to establish WebSocket connection if enabled
    if (useWebSocket) {
      try {
        candleStream = createCandleStream(
          chartSymbol,
          timeframe,
          (candle) => {
            updateCandle(candle)
            setWsConnected(true)
          },
          (error) => {
            console.error('WebSocket error, falling back to polling:', error)
            setWsConnected(false)
            setUseWebSocket(false) // Disable WebSocket to reflect actual state
            // Set up polling as fallback (if not already set up at line 410)
            if (!pollInterval) {
              setupPolling()
            }
          }
        )

        // Still poll periodically to refill window if needed
        pollInterval = window.setInterval(loadInitialCandles, 60_000) // Poll every minute for full refresh
      } catch (err) {
        console.error('Failed to create WebSocket stream:', err)
        setUseWebSocket(false)
        setupPolling()
      }
    } else {
      // Use polling only
      setupPolling()
    }

    return () => {
      mounted = false
      if (candleStream) {
        candleStream.disconnect()
      }
      if (pollInterval) {
        window.clearInterval(pollInterval)
      }
      if (inFlight) {
        inFlight.abort()
      }
    }
  }, [chartSymbol, chartTimeframe, chartLimit, useWebSocket])

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

      const includeAnalysis = activeView === VIEW_IDS.OPPORTUNITIES
      const includeLlm = includeAnalysis
      const analysisLimit = includeAnalysis ? 20 : 5
      const params = new URLSearchParams({
        exchange: 'bitfinex',
        timeframe: chartTimeframe,
        limit: '20',
        include_history: includeAnalysis ? 'true' : 'false',
        include_llm: includeLlm ? 'true' : 'false',
        analysis_limit: analysisLimit.toString(),
      })

      fetch(`/api/signals?${params.toString()}`, { signal: controller.signal })
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
                price: s.price != null ? Number(s.price) : undefined,
                change_24h: s.change_24h != null ? Number(s.change_24h) : undefined,
                rsi: s.rsi != null ? Number(s.rsi) : undefined,
                score_breakdown: Array.isArray(s.score_breakdown) ? s.score_breakdown as Signal['score_breakdown'] : undefined,
                score_explanation: s.score_explanation != null ? String(s.score_explanation) : undefined,
                analysis: s.analysis && typeof s.analysis === 'object' ? s.analysis as Signal['analysis'] : undefined,
                llm: s.llm && typeof s.llm === 'object' ? s.llm as Signal['llm'] : undefined,
                signals: Array.isArray(s.signals) ? s.signals : [],
                created_at: Number(s.created_at || 0),
              }
            })
            .filter((s): s is Signal => s !== null && s.score > 0)

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
  }, [chartTimeframe, activeView])

  // Fetch market watch data
  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setMarketWatchError(null)

      fetch(`/api/market-watch?exchange=bitfinex&timeframe=${encodeURIComponent(chartTimeframe)}`, { signal: controller.signal })
        .then(async (resp) => {
          const bodyText = await resp.text()
          if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${bodyText.slice(0, 120)}`)

          let payload: unknown
          try {
            payload = JSON.parse(bodyText) as unknown
          } catch {
            throw new Error(`Non-JSON response: ${bodyText.slice(0, 120)}`)
          }

          if (!payload || typeof payload !== 'object') throw new Error('Unexpected response format')

          const symbolsData = (payload as { symbols?: unknown }).symbols
          if (!Array.isArray(symbolsData)) throw new Error('Unexpected response format')

          const parsed: MarketWatchItem[] = symbolsData
            .map((item) => {
              if (!item || typeof item !== 'object') return null
              const i = item as Record<string, unknown>
              return {
                symbol: String(i.symbol || ''),
                price: Number(i.price || 0),
                change_1h: Number(i.change_1h || 0),
                change_24h: Number(i.change_24h || 0),
                high_24h: Number(i.high_24h || 0),
                low_24h: Number(i.low_24h || 0),
                volume_24h: Number(i.volume_24h || 0),
                rsi: i.rsi != null ? Number(i.rsi) : null,
                ema_trend: i.ema_trend === 'bullish' ? 'bullish' : 'bearish',
                updated_at: Number(i.updated_at || 0),
              }
            })
            .filter((i): i is MarketWatchItem => i !== null && i.price > 0)

          setMarketWatch(parsed)
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          const message = err instanceof Error ? err.message : 'Unknown error'
          setMarketWatchError(`Unable to load market watch (${message})`)
          setMarketWatch([])
        })
    }

    load()
    const id = window.setInterval(load, MARKET_WATCH_REFRESH_INTERVAL_MS)

    return () => {
      mounted = false
      window.clearInterval(id)
      if (inFlight) inFlight.abort()
    }
  }, [chartTimeframe])

  // Wallet balances - disabled until wallets-data service is deployed
  const WALLETS_SERVICE_ENABLED = false
  useEffect(() => {
    if (!WALLETS_SERVICE_ENABLED) {
      setWalletsLoading(false)
      setWalletsError('Wallet service not yet deployed')
      return
    }

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

          // Support both old format { wallets: [...] } and new format { balances: [...] }
          const p = payload as Record<string, unknown>
          const walletsData = Array.isArray(p.wallets) ? p.wallets : Array.isArray(p.balances) ? p.balances : null
          if (!Array.isArray(walletsData)) throw new Error('Unexpected response format')

          const parsed: Wallet[] = walletsData
            .map((w) => {
              if (!w || typeof w !== 'object') return null
              const wallet = w as Record<string, unknown>
              // Support both old (type,currency,balance,available) and new (currency,total,available,reserved) formats
              return {
                type: String(wallet.type || 'exchange'),
                currency: String(wallet.currency || ''),
                balance: Number(wallet.balance ?? wallet.total ?? 0),
                available: Number(wallet.available || 0),
              }
            })
            .filter((w): w is Wallet => w !== null && w.balance > 0.0001)

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

  // Fetch system status
  useEffect(() => {
    let mounted = true
    let inFlight: AbortController | null = null

    const load = () => {
      if (!mounted) return
      if (inFlight) inFlight.abort()
      const controller = new AbortController()
      inFlight = controller

      setSystemStatusError(null)

      fetchSystemStatus(controller.signal)
        .then((data) => {
          if (!mounted) return
          setSystemStatus(data)
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return
          const message = err instanceof Error ? err.message : 'Unknown error'
          setSystemStatusError(`Unable to fetch system status (${message})`)
          setSystemStatus(null)
        })
    }

    load()
    const id = window.setInterval(load, SYSTEM_STATUS_REFRESH_INTERVAL_MS)

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
    <div className="flex h-screen bg-gray-50 text-sm text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      {/* Sidebar */}
      <Sidebar
        activeViewId={activeView}
        onSelectView={setActiveView}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((v) => !v)}
      />

      {/* Main content area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="flex items-center justify-between px-3 py-2">
            <div className="text-xs font-medium text-gray-600 dark:text-gray-400">
              {activeView.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </div>
            <div className="flex items-center gap-3">

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

        <main className="flex-1 overflow-y-auto px-3 py-3">
          {/* Dashboard view - shows all panels */}
          {activeView === VIEW_IDS.DASHBOARD && (
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
              <Panel title="Chart" subtitle={`Price + volume ${wsConnected ? '(live ⚡)' : '(polling)'}`}>
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
                <Panel title="Orders" subtitle={`${orders.filter(o => o.status === 'PENDING' || o.status === 'ACTIVE').length} active / ${orders.filter(o => o.status === 'FILLED' || o.status === 'EXECUTED').length} filled`}>
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
                {systemStatusError ? (
                  <div className="text-xs text-gray-600 dark:text-gray-400">{systemStatusError}</div>
                ) : systemStatus ? (
                  <>
                    <Kvp
                      k="Backend"
                      v={
                        <span
                          className={
                            systemStatus.backend.status === 'ok'
                              ? 'text-green-600 dark:text-green-400'
                              : 'text-red-600 dark:text-red-400'
                          }
                        >
                          {systemStatus.backend.status === 'ok' ? '✓ OK' : '✗ Error'}
                        </span>
                      }
                    />
                    <div className="mt-2">
                      <Kvp
                        k="Database"
                        v={
                          <span
                            className={
                              systemStatus.database.status === 'ok'
                                ? 'text-green-600 dark:text-green-400'
                                : 'text-red-600 dark:text-red-400'
                            }
                          >
                            {systemStatus.database.status === 'ok'
                              ? `✓ ${systemStatus.database.latency_ms}ms`
                              : '✗ Error'}
                          </span>
                        }
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <Kvp k="Backend" v="—" />
                    <div className="mt-2">
                      <Kvp k="Database" v="—" />
                    </div>
                  </>
                )}
              </Panel>
            </div>
          </div>
          )}

          {/* Chart view - full-width chart */}
          {activeView === VIEW_IDS.CHART && (
            <div className="flex h-full flex-col gap-3">
              <div className="flex items-center gap-2">
                <select
                  value={chartSymbol}
                  onChange={(e) => setChartSymbol(e.target.value)}
                  className="rounded border border-gray-200 bg-white px-2 py-1 text-xs dark:border-gray-700 dark:bg-gray-800"
                >
                  {availableSymbols.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <select
                  value={chartTimeframe}
                  onChange={(e) => setChartTimeframe(e.target.value)}
                  className="rounded border border-gray-200 bg-white px-2 py-1 text-xs dark:border-gray-700 dark:bg-gray-800"
                >
                  {timeframesForChartSymbol.map((tf) => (
                    <option key={tf} value={tf}>{tf}</option>
                  ))}
                </select>
                <span className={`ml-2 text-xs ${wsConnected ? 'text-green-500' : 'text-gray-400'}`}>
                  {wsConnected ? '● Live' : '○ Polling'}
                </span>
              </div>
              <div className="min-h-100 flex-1 rounded border border-gray-200 bg-white p-2 dark:border-gray-700 dark:bg-gray-900">
                <CandlestickChart
                  candles={chartCandles.map((c) => ({
                    time: c.t,
                    open: c.o,
                    high: c.h,
                    low: c.l,
                    close: c.c,
                    volume: c.v,
                  }))}
                  height={500}
                  symbol={chartSymbol}
                  timeframe={chartTimeframe}
                />
              </div>
            </div>
          )}

          {/* Paper Trading Orders view */}
          {activeView === VIEW_IDS.PAPER_ORDERS && (
            <div className="flex flex-col gap-3">
              <Panel title="Place Order" subtitle={`${chartSymbol} @ ${currentPrice?.toFixed(2) || '—'}`}>
                <OrderForm symbol={chartSymbol} currentPrice={currentPrice} onSubmit={handlePlaceOrder} />
              </Panel>
              <Panel title="Open Orders" subtitle={`${orders.length} active`}>
                <OrdersTable orders={orders} onCancel={handleCancelOrder} loading={tradingLoading} />
              </Panel>
            </div>
          )}

          {/* Paper Trading Positions view */}
          {activeView === VIEW_IDS.PAPER_POSITIONS && (
            <Panel title="Open Positions" subtitle={`${positions.length} positions`}>
              <PositionsTable
                positions={positions}
                onClose={handleClosePosition}
                loading={tradingLoading}
              />
            </Panel>
          )}

          {/* Signals view */}
          {activeView === VIEW_IDS.SIGNALS && (
            <Panel title="Trading Signals" subtitle={`${signals.length} opportunities`}>
              {signalsError ? (
                <div className="text-xs text-red-500">{signalsError}</div>
              ) : signals.length === 0 ? (
                <div className="text-xs text-gray-500">No active signals - markets are neutral</div>
              ) : (
                <div className="space-y-2">
                  {signals.map((sig, idx) => {
                    const sideColor = sig.side === 'BUY' ? 'text-green-500' : sig.side === 'SELL' ? 'text-red-500' : 'text-gray-500'
                    const scoreColor = sig.score >= 60 ? 'bg-green-100 dark:bg-green-900' : sig.score >= 40 ? 'bg-yellow-100 dark:bg-yellow-900' : 'bg-gray-100 dark:bg-gray-800'
                    return (
                      <div key={idx} className={`rounded border border-gray-200 p-2 dark:border-gray-700 ${scoreColor}`}>
                        <div className="flex items-center justify-between">
                          <button
                            className="font-medium hover:underline"
                            onClick={() => { setChartSymbol(sig.symbol); setActiveView(VIEW_IDS.CHART); }}
                          >
                            {sig.symbol}
                          </button>
                          <span className={`text-sm font-bold ${sideColor}`}>
                            {sig.side} ({sig.score.toFixed(0)}%)
                          </span>
                        </div>
                        <div className="mt-1 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
                          <span>{sig.timeframe} • RSI: {sig.rsi?.toFixed(0) || '—'}</span>
                          {sig.price && <span>${sig.price.toLocaleString()}</span>}
                        </div>
                        {sig.signals.length > 0 && (
                          <div className="mt-2 space-y-0.5 text-[11px] text-gray-600 dark:text-gray-400">
                            {sig.signals.slice(0, 3).map((s, i) => (
                              <div key={i} className="flex justify-between">
                                <span>• {s.code}</span>
                                <span className={s.side === 'BUY' ? 'text-green-600' : 'text-red-600'}>{s.value}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </Panel>
          )}

          {/* Market Watch view */}
          {activeView === VIEW_IDS.MARKET_WATCH && (
            <Panel title="Market Watch" subtitle={`${marketWatch.length} symbols`}>
              {marketWatchError ? (
                <div className="text-xs text-red-500">{marketWatchError}</div>
              ) : marketWatch.length === 0 ? (
                <div className="text-xs text-gray-500">Loading market data...</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="py-1 text-left font-medium">Symbol</th>
                        <th className="py-1 text-right font-medium">Price</th>
                        <th className="py-1 text-right font-medium">24h %</th>
                        <th className="py-1 text-right font-medium">RSI</th>
                        <th className="py-1 text-right font-medium">Trend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {marketWatch.map((item) => {
                        const changeColor = item.change_24h >= 0 ? 'text-green-500' : 'text-red-500'
                        const rsiColor = item.rsi != null && item.rsi < 30 ? 'text-green-500' : item.rsi != null && item.rsi > 70 ? 'text-red-500' : ''
                        const trendColor = item.ema_trend === 'bullish' ? 'text-green-500' : 'text-red-500'
                        return (
                          <tr
                            key={item.symbol}
                            className="border-b border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800 cursor-pointer"
                            onClick={() => { setChartSymbol(item.symbol); setActiveView(VIEW_IDS.CHART); }}
                          >
                            <td className="py-1.5 font-medium">{item.symbol}</td>
                            <td className="py-1.5 text-right">${item.price.toLocaleString()}</td>
                            <td className={`py-1.5 text-right ${changeColor}`}>
                              {item.change_24h >= 0 ? '+' : ''}{item.change_24h.toFixed(2)}%
                            </td>
                            <td className={`py-1.5 text-right ${rsiColor}`}>
                              {item.rsi?.toFixed(0) || '—'}
                            </td>
                            <td className={`py-1.5 text-right ${trendColor}`}>
                              {item.ema_trend === 'bullish' ? '↑' : '↓'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          )}

          {/* Ingestion Status view */}
          {activeView === VIEW_IDS.INGESTION_STATUS && (
            <Panel title="Data Ingestion" subtitle="Market data service status">
              <div className="space-y-2">
                <Kvp k="API Status" v={ingestionStatus.apiReachable ? '✓ Online' : '✗ Offline'} />
                <Kvp k="Latest BTCUSD-1m" v={ingestionStatus.btcusd1mLatestTime
                  ? new Date(ingestionStatus.btcusd1mLatestTime).toISOString().slice(0, 19).replace('T', ' ')
                  : '—'} />
                {ingestionStatus.gapStats && (
                  <>
                    <Kvp k="Open Gaps" v={ingestionStatus.gapStats.open_gaps} />
                    <Kvp k="Repaired (24h)" v={ingestionStatus.gapStats.repaired_24h} />
                  </>
                )}
              </div>
            </Panel>
          )}

          {/* Wallet view */}
          {activeView === VIEW_IDS.WALLET && (
            <Panel title="Wallet Balances" subtitle="Bitfinex">
              {walletsLoading ? (
                <div className="text-xs text-gray-500">Loading...</div>
              ) : walletsError ? (
                <div className="text-xs text-red-500">{walletsError}</div>
              ) : wallets.length === 0 ? (
                <div className="text-xs text-gray-500">No balances</div>
              ) : (
                <div className="space-y-3">
                  {['exchange', 'margin', 'funding'].map((type) => {
                    const typeWallets = wallets.filter((w) => w.type === type && w.balance !== 0)
                    if (typeWallets.length === 0) return null
                    return (
                      <div key={type}>
                        <div className="mb-1 text-xs font-semibold uppercase text-gray-500">{type}</div>
                        {typeWallets.map((w, i) => (
                          <Kvp key={i} k={w.currency} v={formatCurrency(w.balance, w.currency)} />
                        ))}
                      </div>
                    )
                  })}
                </div>
              )}
            </Panel>
          )}

          {/* Settings view */}
          {activeView === VIEW_IDS.SETTINGS && (
            <Panel title="Settings">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span>Theme</span>
                  <button
                    onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                    className="rounded border border-gray-200 px-3 py-1 text-xs dark:border-gray-700"
                  >
                    {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
                  </button>
                </div>
                <div className="flex items-center justify-between">
                  <span>WebSocket</span>
                  <button
                    onClick={() => setUseWebSocket(!useWebSocket)}
                    className={`rounded px-3 py-1 text-xs ${useWebSocket ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300' : 'bg-gray-100 dark:bg-gray-800'}`}
                  >
                    {useWebSocket ? 'Enabled' : 'Disabled'}
                  </button>
                </div>
              </div>
            </Panel>
          )}

          {/* System Status view */}
          {activeView === VIEW_IDS.SYSTEM_STATUS && (
            <Panel title="System Status">
              {systemStatusError ? (
                <div className="text-xs text-red-500">{systemStatusError}</div>
              ) : systemStatus ? (
                <div className="space-y-2">
                  <Kvp k="Backend" v={systemStatus.backend.status === 'ok' ? '✓ OK' : '✗ Error'} />
                  <Kvp k="Database" v={systemStatus.database.status === 'ok'
                    ? `✓ ${systemStatus.database.latency_ms}ms`
                    : '✗ Error'} />
                  <Kvp k="Uptime" v={`${Math.floor((systemStatus.backend.uptime_seconds || 0) / 60)}m`} />
                </div>
              ) : (
                <div className="text-xs text-gray-500">Loading...</div>
              )}
            </Panel>
          )}

          {/* Opportunities view - shows trading signals */}
          {activeView === VIEW_IDS.OPPORTUNITIES && (
            <Panel title="Trading Opportunities" subtitle={`${signals.length} signals on ${chartTimeframe}`}>
              {signalsError ? (
                <div className="text-xs text-red-500">{signalsError}</div>
              ) : signals.length === 0 ? (
                <div className="py-8 text-center text-gray-500">
                  <div className="text-4xl mb-2">📊</div>
                  <div>No opportunities detected</div>
                  <div className="text-xs mt-1">Try a different timeframe</div>
                </div>
              ) : (
                <div className="space-y-3">
                  {signals.map((sig, idx) => {
                    const sideColor =
                      sig.side === 'BUY'
                        ? 'bg-green-500/20 text-green-400 border-green-500/30'
                        : sig.side === 'SELL'
                          ? 'bg-red-500/20 text-red-400 border-red-500/30'
                          : 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                    const scoreColor =
                      sig.score >= 70
                        ? 'text-green-400'
                        : sig.score >= 50
                          ? 'text-yellow-400'
                          : 'text-gray-400'

                    return (
                      <div
                        key={idx}
                        className="rounded-lg border border-gray-700 bg-gray-800/50 p-3 hover:bg-gray-800 transition-colors cursor-pointer"
                        onClick={() => {
                          setSelectedSymbol(sig.symbol)
                          setActiveView(VIEW_IDS.CHART)
                        }}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-white">{sig.symbol}</span>
                            <span className={`px-2 py-0.5 rounded text-xs font-medium border ${sideColor}`}>
                              {sig.side}
                            </span>
                          </div>
                          <span className={`text-lg font-bold ${scoreColor}`}>{sig.score.toFixed(0)}</span>
                        </div>

                        <div className="flex items-center justify-between text-xs text-gray-400 mb-2">
                          <span>
                            {sig.price != null ? `$${sig.price.toLocaleString()}` : '—'}
                          </span>
                          <span className={sig.change_24h != null && sig.change_24h < 0 ? 'text-red-400' : 'text-green-400'}>
                            {sig.change_24h != null ? `${sig.change_24h >= 0 ? '+' : ''}${sig.change_24h.toFixed(2)}%` : '—'}
                          </span>
                          {sig.rsi != null && (
                            <span className={sig.rsi < 30 ? 'text-green-400' : sig.rsi > 70 ? 'text-red-400' : ''}>
                              RSI {sig.rsi.toFixed(0)}
                            </span>
                          )}
                        </div>

                        {sig.signals.length > 0 && (
                          <div className="space-y-1 text-xs">
                            {sig.signals.map((s, i) => (
                              <div key={i} className="flex items-start gap-2 text-gray-400">
                                <span className={s.side === 'BUY' ? 'text-green-500' : s.side === 'SELL' ? 'text-red-500' : 'text-gray-500'}>
                                  {s.side === 'BUY' ? '▲' : s.side === 'SELL' ? '▼' : '●'}
                                </span>
                                <span>{s.reason}</span>
                              </div>
                            ))}
                          </div>
                        )}

                        {sig.score_breakdown && sig.score_breakdown.length > 0 && (
                          <div className="mt-3 rounded border border-gray-700/60 bg-gray-900/40 p-2 text-[11px] text-gray-300">
                            <div className="font-semibold text-gray-200">Score breakdown</div>
                            <div className="mt-1 space-y-0.5">
                              {sig.score_breakdown.map((item, i) => (
                                <div key={i} className="flex items-center justify-between">
                                  <span className="text-gray-400">{item.code}</span>
                                  <span className="text-gray-200">+{item.contribution.toFixed(1)}</span>
                                </div>
                              ))}
                            </div>
                            {sig.score_explanation && (
                              <div className="mt-1 text-gray-500">{sig.score_explanation}</div>
                            )}
                          </div>
                        )}

                        {sig.analysis && (
                          <div className="mt-3 rounded border border-gray-700/60 bg-gray-900/40 p-2 text-[11px] text-gray-300">
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-gray-200">Historical analysis</span>
                              <span className="text-gray-400">
                                {sig.analysis.recommendation} • {sig.analysis.confidence}%
                              </span>
                            </div>
                            <div className="mt-2 grid grid-cols-2 gap-2 text-gray-400">
                              <div>
                                Support:{' '}
                                <span className="text-gray-200">
                                  {sig.analysis.support_levels?.length ? sig.analysis.support_levels[0].toFixed(2) : '—'}
                                </span>
                              </div>
                              <div>
                                Resistance:{' '}
                                <span className="text-gray-200">
                                  {sig.analysis.resistance_levels?.length ? sig.analysis.resistance_levels[0].toFixed(2) : '—'}
                                </span>
                              </div>
                              <div>
                                ATR:{' '}
                                <span className="text-gray-200">
                                  {sig.analysis.indicators?.atr_percent != null ? `${sig.analysis.indicators.atr_percent.toFixed(2)}%` : '—'}
                                </span>
                              </div>
                              <div>
                                Volume:{' '}
                                <span className="text-gray-200">
                                  {sig.analysis.indicators?.volume_ratio != null ? `${sig.analysis.indicators.volume_ratio.toFixed(1)}x` : '—'}
                                </span>
                              </div>
                            </div>
                            {sig.analysis.reasoning?.length > 0 && (
                              <div className="mt-2 space-y-0.5 text-gray-400">
                                {sig.analysis.reasoning.slice(0, 3).map((reason, i) => (
                                  <div key={i}>• {reason}</div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {sig.llm?.summary && (
                          <div className="mt-3 rounded border border-blue-500/30 bg-blue-500/10 p-2 text-[11px] text-blue-100">
                            <div className="font-semibold text-blue-200">LLM summary</div>
                            <div className="mt-1 text-blue-100">{sig.llm.summary}</div>
                            {sig.llm.explanation && (
                              <div className="mt-1 text-blue-200/80">{sig.llm.explanation}</div>
                            )}
                            {sig.llm.risks && (
                              <div className="mt-1 text-blue-200/70">Risks: {sig.llm.risks}</div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </Panel>
          )}
        </main>

        <footer className="border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="flex items-center justify-between px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
            <span>v2 skeleton</span>
            <span>paper-trading default</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
