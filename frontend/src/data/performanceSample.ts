import type { EquityPoint } from '../components/PerformanceCharts'

/**
 * Sample performance data used for the dashboard equity/drawdown charts.
 * Represents a short equity curve from a backtest run.
 */
export const sampleEquityCurve: EquityPoint[] = [
  { time: 0, value: 10000 },
  { time: 1, value: 10250 },
  { time: 2, value: 10120 },
  { time: 3, value: 10500 },
  { time: 4, value: 9920 },
  { time: 5, value: 10840 },
  { time: 6, value: 11275 },
  { time: 7, value: 11010 },
  { time: 8, value: 11780 },
  { time: 9, value: 12350 },
  { time: 10, value: 12120 },
  { time: 11, value: 12940 },
]
