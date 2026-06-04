import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import PerformanceCharts from '../components/PerformanceCharts'
import type { EquityPoint } from '../types/performance'

vi.mock('lightweight-charts', () => {
  const setData = vi.fn()
  const addSeries = vi.fn(() => ({ setData }))
  const timeScale = () => ({ fitContent: vi.fn() })
  const chartStub = {
    addSeries,
    applyOptions: vi.fn(),
    timeScale,
    remove: vi.fn(),
  }
  return {
    ColorType: { Solid: 'solid' },
    LineSeries: 'LineSeries',
    createChart: vi.fn(() => chartStub),
  }
})

const sampleCurve: EquityPoint[] = [
  { time: { year: 2024, month: 1, day: 1 }, value: 10000 },
  { time: { year: 2024, month: 1, day: 2 }, value: 10500 },
  { time: { year: 2024, month: 1, day: 3 }, value: 10200 },
  { time: { year: 2024, month: 1, day: 4 }, value: 11000 },
]

describe('PerformanceCharts', () => {
  it('renders summary stats for equity and drawdown', () => {
    render(<PerformanceCharts equityCurve={sampleCurve} />)

    expect(screen.getByText(/Final equity/i)).toBeInTheDocument()
    expect(screen.getByText(/11[.,\s]?000/)).toBeInTheDocument()
    expect(screen.getByText(/Max drawdown/i)).toBeInTheDocument()
    expect(screen.getByText(/-2\.86%/)).toBeInTheDocument()
  })

  it('shows fallback when no data is available', () => {
    render(<PerformanceCharts equityCurve={[]} />)
    expect(screen.getByText(/No performance data available/i)).toBeInTheDocument()
  })
})
