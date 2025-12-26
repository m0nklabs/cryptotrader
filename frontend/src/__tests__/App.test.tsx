import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
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
  fetchMarketCap: vi.fn().mockResolvedValue({}),
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
    status: 'healthy',
    uptime_seconds: 100,
    database: { connected: true },
  }),
}))

describe('App Component', () => {
  beforeEach(() => {
    // Mock localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(() => 'dark'),
        setItem: vi.fn(),
      },
      writable: true,
    })
  })

  it('renders without crashing', () => {
    render(<App />)
    expect(document.body).toBeTruthy()
  })

  it('renders the main application layout', () => {
    render(<App />)
    // Check that the app container exists with a more specific selector
    const appElement = document.querySelector('[class*="min-h-screen"]')
    expect(appElement).toBeInTheDocument()
  })

  it('applies dark mode by default', () => {
    const { container } = render(<App />)
    // Verify the component is rendered and dark mode class is applied
    expect(container.firstChild).toBeTruthy()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
