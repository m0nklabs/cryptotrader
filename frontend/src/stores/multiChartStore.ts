/**
 * Multi-Chart Store
 * =================
 * Manages state for multi-timeframe chart view
 */

import { create } from 'zustand'

export type TimeframePreset = 'scalper' | 'swing' | 'position' | 'custom'

export type ChartConfig = {
  id: string
  symbol: string
  timeframe: string
  visible: boolean
}

type MultiChartState = {
  charts: ChartConfig[]
  preset: TimeframePreset
  crosshairTime: number | null
  
  // Actions
  setCharts: (charts: ChartConfig[]) => void
  updateChart: (id: string, updates: Partial<ChartConfig>) => void
  setPreset: (preset: TimeframePreset) => void
  setCrosshairTime: (time: number | null) => void
  applyPreset: (preset: TimeframePreset, symbol: string) => void
}

const PRESETS: Record<TimeframePreset, string[]> = {
  scalper: ['1m', '5m', '15m'],
  swing: ['1h', '4h', '1d'],
  position: ['4h', '1d', '1w'],
  custom: [],
}

export const useMultiChartStore = create<MultiChartState>((set) => ({
  charts: [],
  preset: 'swing',
  crosshairTime: null,

  setCharts: (charts) => set({ charts }),

  updateChart: (id, updates) =>
    set((state) => ({
      charts: state.charts.map((chart) =>
        chart.id === id ? { ...chart, ...updates } : chart
      ),
    })),

  setPreset: (preset) => set({ preset }),

  setCrosshairTime: (time) => set({ crosshairTime: time }),

  applyPreset: (preset, symbol) => {
    const timeframes = PRESETS[preset]
    if (timeframes.length === 0) return

    const charts: ChartConfig[] = timeframes.map((tf, idx) => ({
      id: `chart-${idx}`,
      symbol,
      timeframe: tf,
      visible: true,
    }))

    set({ charts, preset })
  },
}))
