import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type WebSocketStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error'

type UseWebSocketOptions<T> = {
  url: string
  enabled?: boolean
  protocols?: string | string[]
  reconnect?: boolean
  maxReconnectAttempts?: number
  initialReconnectDelayMs?: number
  maxReconnectDelayMs?: number
  subscribeMessage?: Record<string, unknown> | null
  onMessage: (data: T) => void
  onStatusChange?: (status: WebSocketStatus) => void
}

export function useWebSocket<T = unknown>({
  url,
  enabled = true,
  protocols,
  reconnect = true,
  maxReconnectAttempts = 5,
  initialReconnectDelayMs = 1000,
  maxReconnectDelayMs = 30000,
  subscribeMessage = null,
  onMessage,
  onStatusChange,
}: UseWebSocketOptions<T>) {
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const [status, setStatus] = useState<WebSocketStatus>('idle')

  const subscribePayload = useMemo(
    () => (subscribeMessage ? JSON.stringify(subscribeMessage) : null),
    [subscribeMessage]
  )

  const updateStatus = useCallback(
    (next: WebSocketStatus) => {
      setStatus(next)
      onStatusChange?.(next)
    },
    [onStatusChange]
  )

  const sendJson = useCallback((payload: Record<string, unknown>) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(payload))
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      updateStatus('idle')
      return undefined
    }

    if (typeof WebSocket === 'undefined') {
      updateStatus('error')
      return undefined
    }

    let active = true

    const connect = () => {
      if (!active) return
      updateStatus('connecting')

      const resolvedUrl = url.startsWith('/')
        ? new URL(url, window.location.origin)
        : new URL(url)
      if (resolvedUrl.protocol === 'http:') {
        resolvedUrl.protocol = 'ws:'
      } else if (resolvedUrl.protocol === 'https:') {
        resolvedUrl.protocol = 'wss:'
      }
      const socket = new WebSocket(resolvedUrl.toString(), protocols)
      socketRef.current = socket

      socket.onopen = () => {
        reconnectAttemptsRef.current = 0
        updateStatus('connected')
        if (subscribePayload) {
          socket.send(subscribePayload)
        }
      }

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as T
          onMessage(data)
        } catch (err) {
          console.error('[WebSocket] Failed to parse message', err)
        }
      }

      socket.onerror = () => {
        updateStatus('error')
      }

      socket.onclose = () => {
        if (!active) return
        updateStatus('disconnected')

        if (!reconnect) return
        if (reconnectAttemptsRef.current >= maxReconnectAttempts) return

        reconnectAttemptsRef.current += 1
        const delay = Math.min(
          initialReconnectDelayMs * Math.pow(2, reconnectAttemptsRef.current - 1),
          maxReconnectDelayMs
        )
        reconnectTimeoutRef.current = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      active = false
      if (reconnectTimeoutRef.current !== null) {
        window.clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (socketRef.current) {
        socketRef.current.close()
        socketRef.current = null
      }
    }
  }, [
    enabled,
    initialReconnectDelayMs,
    maxReconnectAttempts,
    maxReconnectDelayMs,
    onMessage,
    protocols,
    reconnect,
    subscribePayload,
    updateStatus,
    url,
  ])

  return { status, sendJson }
}
