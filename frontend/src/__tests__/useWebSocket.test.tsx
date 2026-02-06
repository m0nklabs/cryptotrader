import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useWebSocket } from '../hooks/useWebSocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0
  sent: string[] = []
  closeCalled = false
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.closeCalled = true
    this.readyState = 3
    this.onclose?.()
  }

  triggerOpen() {
    this.readyState = 1
    this.onopen?.()
  }

  triggerMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }

  triggerClose() {
    this.readyState = 3
    this.onclose?.()
  }
}

function HookHarness({ url, onMessage, subscribeMessage }: { url: string; onMessage: (data: unknown) => void; subscribeMessage?: Record<string, unknown> }) {
  useWebSocket({
    url,
    onMessage,
    subscribeMessage,
  })
  return null
}

describe('useWebSocket', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('connects and forwards messages', () => {
    const onMessage = vi.fn()
    const { unmount } = render(<HookHarness url="http://localhost/ws" onMessage={onMessage} subscribeMessage={{ type: 'subscribe' }} />)

    const ws = MockWebSocket.instances[0]
    act(() => ws.triggerOpen())
    act(() => ws.triggerMessage({ hello: 'world' }))

    expect(onMessage).toHaveBeenCalledWith({ hello: 'world' })
    expect(ws.sent[0]).toBe(JSON.stringify({ type: 'subscribe' }))

    unmount()
    expect(ws.closeCalled).toBe(true)
  })

  it('reconnects after close', () => {
    vi.useFakeTimers()
    const onMessage = vi.fn()
    render(<HookHarness url="http://localhost/ws" onMessage={onMessage} />)

    const ws = MockWebSocket.instances[0]
    act(() => ws.triggerOpen())
    act(() => ws.triggerClose())

    act(() => {
      vi.runOnlyPendingTimers()
    })

    expect(MockWebSocket.instances.length).toBe(2)
  })

  it('resolves relative urls to ws protocol', () => {
    const onMessage = vi.fn()
    render(<HookHarness url="/ws/prices" onMessage={onMessage} />)

    const ws = MockWebSocket.instances[0]
    expect(ws.url.startsWith('ws://')).toBe(true)
  })
})
