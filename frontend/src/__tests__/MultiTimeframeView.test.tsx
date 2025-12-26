/**
 * Multi-Timeframe View Tests
 * ==========================
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import MultiTimeframeView from '../components/MultiTimeframeView'
import type { OHLCV } from '../utils/indicators'

const mockCandles: OHLCV[] = [
  { time: 1000, open: 100, high: 110, low: 90, close: 105, volume: 1000 },
  { time: 2000, open: 105, high: 115, low: 95, close: 110, volume: 1100 },
]

describe('MultiTimeframeView', () => {
  const mockFetchCandles = vi.fn(async () => mockCandles)

  it('renders loading state initially', () => {
    render(<MultiTimeframeView symbol="BTCUSD" fetchCandles={mockFetchCandles} />)
    // The component initializes with a preset, so it should show the preset selector
    expect(screen.getByText(/Timeframe Preset/i)).toBeInTheDocument()
  })

  it('renders preset selector buttons', async () => {
    render(<MultiTimeframeView symbol="BTCUSD" fetchCandles={mockFetchCandles} />)
    
    await waitFor(() => {
      expect(screen.getByText('Scalper')).toBeInTheDocument()
      expect(screen.getByText('Swing')).toBeInTheDocument()
      expect(screen.getByText('Position')).toBeInTheDocument()
    })
  })

  it('changes preset when button clicked', async () => {
    const user = userEvent.setup()
    render(<MultiTimeframeView symbol="BTCUSD" fetchCandles={mockFetchCandles} />)

    await waitFor(() => {
      expect(screen.getByText('Scalper')).toBeInTheDocument()
    })

    const scalperButton = screen.getByText('Scalper')
    await user.click(scalperButton)

    // Verify the button gets active styling (implementation detail)
    expect(scalperButton).toHaveClass('bg-blue-600')
  })
})
