/**
 * CandlestickChart Component
 * ==========================
 * TradingView-style candlestick chart with indicator overlays using lightweight-charts v5
 */

import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type HistogramData,
  ColorType,
} from 'lightweight-charts'
import {
  calculateRSI,
  calculateMACD,
  calculateBollingerBands,
  calculateStochastic,
  type OHLCV,
} from '../utils/indicators'

type IndicatorState = {
  rsi: boolean
  macd: boolean
  bollinger: boolean
  stochastic: boolean
}

type Props = {
  candles: OHLCV[]
  symbol: string
  timeframe: string
  height?: number
}

const CHART_COLORS = {
  background: '#0f172a',
  textColor: '#94a3b8',
  gridColor: '#1e293b',
  upColor: '#22c55e',
  downColor: '#ef4444',
  borderUpColor: '#22c55e',
  borderDownColor: '#ef4444',
  wickUpColor: '#22c55e',
  wickDownColor: '#ef4444',
}

const INDICATOR_COLORS = {
  rsi: '#eab308',
  macdLine: '#3b82f6',
  signalLine: '#f97316',
  histogramUp: '#22c55e',
  histogramDown: '#ef4444',
  bollingerUpper: '#a855f7',
  bollingerMiddle: '#8b5cf6',
  bollingerLower: '#a855f7',
  stochK: '#06b6d4',
  stochD: '#f43f5e',
}

export default function CandlestickChart({ candles, symbol, timeframe, height = 400 }: Props) {
  const mainChartRef = useRef<HTMLDivElement>(null)
  const rsiChartRef = useRef<HTMLDivElement>(null)
  const macdChartRef = useRef<HTMLDivElement>(null)
  const stochChartRef = useRef<HTMLDivElement>(null)

  const mainChart = useRef<IChartApi | null>(null)
  const rsiChart = useRef<IChartApi | null>(null)
  const macdChart = useRef<IChartApi | null>(null)
  const stochChart = useRef<IChartApi | null>(null)

  const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const bollingerUpper = useRef<ISeriesApi<'Line'> | null>(null)
  const bollingerMiddle = useRef<ISeriesApi<'Line'> | null>(null)
  const bollingerLower = useRef<ISeriesApi<'Line'> | null>(null)

  const [indicators, setIndicators] = useState<IndicatorState>({
    rsi: false,
    macd: false,
    bollinger: false,
    stochastic: false,
  })

  const toggleIndicator = (key: keyof IndicatorState) => {
    setIndicators((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  // Create main chart
  useEffect(() => {
    if (!mainChartRef.current) return

    const chart = createChart(mainChartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.textColor,
      },
      grid: {
        vertLines: { color: CHART_COLORS.gridColor },
        horzLines: { color: CHART_COLORS.gridColor },
      },
      width: mainChartRef.current.clientWidth,
      height: height,
      crosshair: {
        mode: 1,
      },
      timeScale: {
        borderColor: CHART_COLORS.gridColor,
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: CHART_COLORS.gridColor,
      },
    })

    mainChart.current = chart

    // Candlestick series (v5 API)
    const series = chart.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.upColor,
      downColor: CHART_COLORS.downColor,
      borderUpColor: CHART_COLORS.borderUpColor,
      borderDownColor: CHART_COLORS.borderDownColor,
      wickUpColor: CHART_COLORS.wickUpColor,
      wickDownColor: CHART_COLORS.wickDownColor,
    })
    candleSeries.current = series

    // Bollinger Bands (initially hidden)
    bollingerUpper.current = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.bollingerUpper,
      lineWidth: 1,
      visible: false,
    })
    bollingerMiddle.current = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.bollingerMiddle,
      lineWidth: 1,
      visible: false,
    })
    bollingerLower.current = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.bollingerLower,
      lineWidth: 1,
      visible: false,
    })

    // Resize handler
    const handleResize = () => {
      if (mainChartRef.current) {
        chart.applyOptions({ width: mainChartRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [height])

  // Update candle data
  useEffect(() => {
    if (!candleSeries.current || candles.length === 0) return

    const data: CandlestickData[] = candles.map((c) => ({
      time: c.time as CandlestickData['time'],
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))

    candleSeries.current.setData(data)

    // Fit content
    mainChart.current?.timeScale().fitContent()
  }, [candles])

  // Update Bollinger Bands
  useEffect(() => {
    if (!bollingerUpper.current || !bollingerMiddle.current || !bollingerLower.current) return

    bollingerUpper.current.applyOptions({ visible: indicators.bollinger })
    bollingerMiddle.current.applyOptions({ visible: indicators.bollinger })
    bollingerLower.current.applyOptions({ visible: indicators.bollinger })

    if (indicators.bollinger && candles.length > 20) {
      const bb = calculateBollingerBands(candles)
      bollingerUpper.current.setData(bb.map((b) => ({ time: b.time as LineData['time'], value: b.upper })))
      bollingerMiddle.current.setData(bb.map((b) => ({ time: b.time as LineData['time'], value: b.middle })))
      bollingerLower.current.setData(bb.map((b) => ({ time: b.time as LineData['time'], value: b.lower })))
    }
  }, [indicators.bollinger, candles])

  // RSI sub-chart
  useEffect(() => {
    if (!indicators.rsi) {
      if (rsiChart.current) {
        rsiChart.current.remove()
        rsiChart.current = null
      }
      return
    }

    if (!rsiChartRef.current || rsiChart.current) return

    const chart = createChart(rsiChartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.textColor,
      },
      grid: {
        vertLines: { color: CHART_COLORS.gridColor },
        horzLines: { color: CHART_COLORS.gridColor },
      },
      width: rsiChartRef.current.clientWidth,
      height: 100,
      timeScale: { visible: false },
      rightPriceScale: {
        borderColor: CHART_COLORS.gridColor,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
    })

    rsiChart.current = chart

    const series = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.rsi,
      lineWidth: 2,
    })

    const rsiData = calculateRSI(candles)
    series.setData(rsiData.map((r) => ({ time: r.time as LineData['time'], value: r.value })))

    // Overbought/oversold lines
    const overbought = chart.addSeries(LineSeries, { color: '#ef444480', lineWidth: 1, lineStyle: 2 })
    const oversold = chart.addSeries(LineSeries, { color: '#22c55e80', lineWidth: 1, lineStyle: 2 })

    if (rsiData.length > 0) {
      const times = rsiData.map((r) => r.time)
      overbought.setData(times.map((t) => ({ time: t as LineData['time'], value: 70 })))
      oversold.setData(times.map((t) => ({ time: t as LineData['time'], value: 30 })))
    }

    // Sync time scale
    if (mainChart.current) {
      mainChart.current.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) chart.timeScale().setVisibleLogicalRange(range)
      })
    }

    return () => {
      chart.remove()
      rsiChart.current = null
    }
  }, [indicators.rsi, candles])

  // MACD sub-chart
  useEffect(() => {
    if (!indicators.macd) {
      if (macdChart.current) {
        macdChart.current.remove()
        macdChart.current = null
      }
      return
    }

    if (!macdChartRef.current || macdChart.current) return

    const chart = createChart(macdChartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.textColor,
      },
      grid: {
        vertLines: { color: CHART_COLORS.gridColor },
        horzLines: { color: CHART_COLORS.gridColor },
      },
      width: macdChartRef.current.clientWidth,
      height: 120,
      timeScale: { visible: false },
      rightPriceScale: { borderColor: CHART_COLORS.gridColor },
    })

    macdChart.current = chart

    const macdData = calculateMACD(candles)

    // Histogram
    const histogram = chart.addSeries(HistogramSeries, {
      color: INDICATOR_COLORS.histogramUp,
    })
    histogram.setData(
      macdData.map((m) => ({
        time: m.time as HistogramData['time'],
        value: m.histogram,
        color: m.histogram >= 0 ? INDICATOR_COLORS.histogramUp : INDICATOR_COLORS.histogramDown,
      }))
    )

    // MACD line
    const macdLine = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.macdLine,
      lineWidth: 2,
    })
    macdLine.setData(macdData.map((m) => ({ time: m.time as LineData['time'], value: m.macd })))

    // Signal line
    const signalLine = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.signalLine,
      lineWidth: 2,
    })
    signalLine.setData(macdData.map((m) => ({ time: m.time as LineData['time'], value: m.signal })))

    // Sync time scale
    if (mainChart.current) {
      mainChart.current.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) chart.timeScale().setVisibleLogicalRange(range)
      })
    }

    return () => {
      chart.remove()
      macdChart.current = null
    }
  }, [indicators.macd, candles])

  // Stochastic sub-chart
  useEffect(() => {
    if (!indicators.stochastic) {
      if (stochChart.current) {
        stochChart.current.remove()
        stochChart.current = null
      }
      return
    }

    if (!stochChartRef.current || stochChart.current) return

    const chart = createChart(stochChartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.textColor,
      },
      grid: {
        vertLines: { color: CHART_COLORS.gridColor },
        horzLines: { color: CHART_COLORS.gridColor },
      },
      width: stochChartRef.current.clientWidth,
      height: 100,
      timeScale: { visible: false },
      rightPriceScale: {
        borderColor: CHART_COLORS.gridColor,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
    })

    stochChart.current = chart

    const stochData = calculateStochastic(candles)

    const kLine = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.stochK,
      lineWidth: 2,
    })
    kLine.setData(stochData.map((s) => ({ time: s.time as LineData['time'], value: s.k })))

    const dLine = chart.addSeries(LineSeries, {
      color: INDICATOR_COLORS.stochD,
      lineWidth: 2,
    })
    dLine.setData(stochData.map((s) => ({ time: s.time as LineData['time'], value: s.d })))

    // Overbought/oversold
    if (stochData.length > 0) {
      const times = stochData.map((s) => s.time)
      const overbought = chart.addSeries(LineSeries, { color: '#ef444480', lineWidth: 1, lineStyle: 2 })
      const oversold = chart.addSeries(LineSeries, { color: '#22c55e80', lineWidth: 1, lineStyle: 2 })
      overbought.setData(times.map((t) => ({ time: t as LineData['time'], value: 80 })))
      oversold.setData(times.map((t) => ({ time: t as LineData['time'], value: 20 })))
    }

    // Sync time scale
    if (mainChart.current) {
      mainChart.current.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) chart.timeScale().setVisibleLogicalRange(range)
      })
    }

    return () => {
      chart.remove()
      stochChart.current = null
    }
  }, [indicators.stochastic, candles])

  return (
    <div className="flex flex-col gap-1">
      {/* Header with indicator toggles */}
      <div className="flex items-center gap-2 text-xs">
        <span className="font-semibold text-gray-200">
          {symbol} · {timeframe}
        </span>
        <div className="ml-auto flex gap-1">
          <IndicatorButton
            label="BB"
            active={indicators.bollinger}
            onClick={() => toggleIndicator('bollinger')}
            color={INDICATOR_COLORS.bollingerMiddle}
          />
          <IndicatorButton
            label="RSI"
            active={indicators.rsi}
            onClick={() => toggleIndicator('rsi')}
            color={INDICATOR_COLORS.rsi}
          />
          <IndicatorButton
            label="MACD"
            active={indicators.macd}
            onClick={() => toggleIndicator('macd')}
            color={INDICATOR_COLORS.macdLine}
          />
          <IndicatorButton
            label="Stoch"
            active={indicators.stochastic}
            onClick={() => toggleIndicator('stochastic')}
            color={INDICATOR_COLORS.stochK}
          />
        </div>
      </div>

      {/* Main candlestick chart */}
      <div ref={mainChartRef} className="w-full rounded border border-gray-800" />

      {/* RSI sub-chart */}
      {indicators.rsi && (
        <div className="flex items-center gap-2">
          <span className="w-12 text-right text-xs text-yellow-500">RSI</span>
          <div ref={rsiChartRef} className="flex-1 rounded border border-gray-800" />
        </div>
      )}

      {/* MACD sub-chart */}
      {indicators.macd && (
        <div className="flex items-center gap-2">
          <span className="w-12 text-right text-xs text-blue-500">MACD</span>
          <div ref={macdChartRef} className="flex-1 rounded border border-gray-800" />
        </div>
      )}

      {/* Stochastic sub-chart */}
      {indicators.stochastic && (
        <div className="flex items-center gap-2">
          <span className="w-12 text-right text-xs text-cyan-500">Stoch</span>
          <div ref={stochChartRef} className="flex-1 rounded border border-gray-800" />
        </div>
      )}
    </div>
  )
}

function IndicatorButton({
  label,
  active,
  onClick,
  color,
}: {
  label: string
  active: boolean
  onClick: () => void
  color: string
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
        active
          ? 'text-white'
          : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300'
      }`}
      style={active ? { backgroundColor: color } : undefined}
    >
      {label}
    </button>
  )
}
