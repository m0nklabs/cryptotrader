import { useEffect, useMemo } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { usePriceStore, type PriceStatus } from '../stores/priceStore'

type LivePriceProps = {
  symbol: string
  exchange: string
  timeframe: string
  className?: string
}

type PriceMessage = {
  type?: string
  exchange?: string
  symbol?: string
  price?: number
  timestamp?: number
  status?: string
}

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function LivePrice({ symbol, exchange, timeframe, className }: LivePriceProps) {
  const setPrice = usePriceStore((state) => state.setPrice)
  const setStatus = usePriceStore((state) => state.setStatus)
  const priceSnapshot = usePriceStore((state) => state.prices[`${exchange}:${symbol}`])
  const status = usePriceStore((state) => state.statusByExchange[exchange] || 'disconnected')

  const socketUrl = useMemo(() => {
    if (API_BASE) {
      const base = API_BASE.replace(/^http/, 'ws')
      return `${base}/ws/prices`
    }
    const { protocol, host } = window.location
    const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'
    return `${wsProtocol}//${host}/api/ws/prices`
  }, [])

  useWebSocket<PriceMessage>({
    url: socketUrl,
    enabled: Boolean(symbol),
    subscribeMessage: {
      type: 'subscribe',
      exchange,
      symbols: [symbol],
    },
    onMessage: (data) => {
      if (data.type === 'status' && data.exchange && data.status) {
        setStatus(data.exchange, data.status as PriceStatus)
        return
      }
      if (data.type === 'price' && data.exchange && data.symbol && typeof data.price === 'number') {
        setPrice({
          exchange: data.exchange,
          symbol: data.symbol,
          price: data.price,
          timestamp: data.timestamp ?? Date.now(),
        })
        setStatus(data.exchange, 'connected')
      }
    },
    onStatusChange: (next) => {
      if (next === 'connected') return
      setStatus(exchange, next === 'connecting' ? 'connecting' : 'disconnected')
    },
  })

  useEffect(() => {
    if (status === 'connected') return undefined
    if (!symbol) return undefined
    if (typeof fetch === 'undefined') return undefined

    let cancelled = false
    const controller = new AbortController()

    const poll = async () => {
      try {
        const fetchBaseUrl = API_BASE || window.location.origin
        const url = `${fetchBaseUrl}/candles/latest?exchange=${encodeURIComponent(exchange)}&symbol=${encodeURIComponent(
          symbol
        )}&timeframe=${encodeURIComponent(timeframe)}&limit=1`
        const resp = await fetch(url, { signal: controller.signal })
        if (!resp.ok) return
        const payload = await resp.json()
        const candles = Array.isArray(payload.candles) ? payload.candles : []
        const latest = candles[candles.length - 1]
        if (latest && typeof latest.close === 'number' && !cancelled) {
          setPrice({
            exchange,
            symbol,
            price: latest.close,
            timestamp: latest.open_time_ms ?? Date.now(),
          })
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        console.warn('[LivePrice] Polling failed', err)
        setStatus(exchange, 'error')
      }
    }

    poll()
    const id = window.setInterval(poll, 15000)

    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(id)
    }
  }, [exchange, symbol, status, setPrice, timeframe])

  const statusColor =
    status === 'connected'
      ? 'bg-green-500'
      : status === 'connecting'
        ? 'bg-yellow-500'
        : 'bg-gray-400'

  return (
    <div className={`flex items-center gap-2 text-xs ${className || ''}`}>
      <span className={`h-2 w-2 rounded-full ${statusColor}`} />
      <span className="text-gray-600 dark:text-gray-400">{exchange}</span>
      <span className="font-semibold">{priceSnapshot ? `$${priceSnapshot.price.toFixed(2)}` : '—'}</span>
    </div>
  )
}
