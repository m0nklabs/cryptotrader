import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '../App'

// Mock API modules
vi.mock('../api/trading', () => ({
  placeOrder: vi.fn(),
  listOrders: vi.fn().mockResolvedValue([]),
  cancelOrder: vi.fn(),
  listPositions: vi.fn().mockResolvedValue([]),
  closePosition: vi.fn(),
}))

vi.mock('../api/marketCap', () => ({
  fetchMarketCap: vi.fn().mockResolvedValue({ rankings: {}, source: 'fallback' }),
}))

vi.mock('../api/candleStream', () => ({
  createCandleStream: vi.fn().mockReturnValue({
    subscribe: vi.fn(),
    close: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

vi.mock('../api/systemStatus', () => ({
  fetchSystemStatus: vi.fn().mockResolvedValue({
    backend: { status: 'ok', uptime_seconds: 100 },
    database: { status: 'ok', connected: true, latency_ms: 12 },
    timestamp: 0,
  }),
}))

describe('App Component', () => {
  beforeEach(() => {
    // Mock localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(() => 'dark'),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      },
      writable: true,
    })
  })

  it('renders without crashing', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    )
    expect(container.firstChild).toBeTruthy()
  })

  it('renders the main application layout', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    )
    // Check that the app container exists with a more specific selector
    // The main container uses h-screen, not min-h-screen
    const appElement = document.querySelector('[class*="h-screen"]')
    expect(appElement).toBeInTheDocument()
  })

  it('applies dark mode by default', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    )
    // Verify the component is rendered and dark mode class is applied
    expect(container.firstChild).toBeTruthy()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
