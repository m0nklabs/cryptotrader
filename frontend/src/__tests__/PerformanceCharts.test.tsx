import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import PerformanceCharts, { type EquityPoint } from '../components/PerformanceCharts'

const sampleCurve: EquityPoint[] = [
  { time: 0, value: 10000 },
  { time: 1, value: 10500 },
  { time: 2, value: 10200 },
  { time: 3, value: 11000 },
]

describe('PerformanceCharts', () => {
  it('renders summary stats for equity and drawdown', () => {
    render(<PerformanceCharts equityCurve={sampleCurve} />)

    expect(screen.getByText(/Final equity/i)).toBeInTheDocument()
    expect(screen.getByText(/\$11,000/)).toBeInTheDocument()
    expect(screen.getByText(/Max drawdown/i)).toBeInTheDocument()
    expect(screen.getByText(/-2\.86%/)).toBeInTheDocument()
  })

  it('shows fallback when no data is available', () => {
    render(<PerformanceCharts equityCurve={[]} />)
    expect(screen.getByText(/No performance data available/i)).toBeInTheDocument()
  })
})
