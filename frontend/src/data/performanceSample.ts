import type { EquityPoint } from '../types/performance'

/**
 * Sample performance data used for the dashboard equity/drawdown charts.
 * Represents a short equity curve from a backtest run.
 */
export const sampleEquityCurve: EquityPoint[] = [
  { time: { year: 2024, month: 1, day: 1 }, value: 10000 },
  { time: { year: 2024, month: 1, day: 2 }, value: 10250 },
  { time: { year: 2024, month: 1, day: 3 }, value: 10120 },
  { time: { year: 2024, month: 1, day: 4 }, value: 10500 },
  { time: { year: 2024, month: 1, day: 5 }, value: 9920 },
  { time: { year: 2024, month: 1, day: 6 }, value: 10840 },
  { time: { year: 2024, month: 1, day: 7 }, value: 11275 },
  { time: { year: 2024, month: 1, day: 8 }, value: 11010 },
  { time: { year: 2024, month: 1, day: 9 }, value: 11780 },
  { time: { year: 2024, month: 1, day: 10 }, value: 12350 },
  { time: { year: 2024, month: 1, day: 11 }, value: 12120 },
  { time: { year: 2024, month: 1, day: 12 }, value: 12940 },
]
