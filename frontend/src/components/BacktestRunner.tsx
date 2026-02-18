/**
 * Backtest Runner Component
 * ==========================
 * Configure and execute backtests on historical data
 */

import { useState, useEffect } from 'react'
import { runBacktest, listStrategies, type BacktestRequest, type BacktestResult, type StrategyInfo } from '../api/backtest'

type Props = {
  onResultsReady?: (results: BacktestResult) => void
}

export default function BacktestRunner({ onResultsReady }: Props) {
  // Form state
  const [exchange, setExchange] = useState('bitfinex')
  const [symbol, setSymbol] = useState('BTCUSD')
  const [timeframe, setTimeframe] = useState('1h')
  const [strategy, setStrategy] = useState<'rsi'>('rsi')
  const [initialCapital, setInitialCapital] = useState(10000)
  const [daysBack, setDaysBack] = useState(30)

  // RSI parameters
  const [rsiOversold, setRsiOversold] = useState(30)
  const [rsiOverbought, setRsiOverbought] = useState(70)

  // UI state
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])

  // Load available strategies
  useEffect(() => {
    listStrategies()
      .then(setStrategies)
      .catch((err) => console.error('Failed to load strategies:', err))
  }, [])

  const handleRun = async () => {
    setRunning(true)
    setError(null)

    try {
      // Calculate date range
      const endDate = new Date()
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - daysBack)

      const request: BacktestRequest = {
        exchange,
        symbol,
        timeframe,
        strategy,
        start_date: startDate.toISOString(),
        end_date: endDate.toISOString(),
        initial_capital: initialCapital,
        rsi_oversold: rsiOversold,
        rsi_overbought: rsiOverbought,
      }

      const result = await runBacktest(request)

      if (onResultsReady) {
        onResultsReady(result)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="bg-[#1a1a2e] p-4 rounded border border-zinc-700">
      <h2 className="text-lg font-semibold mb-4 text-zinc-100">Backtest Configuration</h2>

      {/* Market Selection */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Exchange</label>
          <input
            type="text"
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Timeframe</label>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
          >
            <option value="1m">1m</option>
            <option value="5m">5m</option>
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
            <option value="1d">1d</option>
          </select>
        </div>
      </div>

      {/* Strategy & Capital */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Strategy</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value as 'rsi')}
            className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
          >
            {strategies.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Initial Capital ($)</label>
          <input
            type="number"
            value={initialCapital}
            onChange={(e) => setInitialCapital(Number(e.target.value))}
            min={100}
            step={1000}
            className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Days Back</label>
          <input
            type="number"
            value={daysBack}
            onChange={(e) => setDaysBack(Number(e.target.value))}
            min={1}
            max={365}
            className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
          />
        </div>
      </div>

      {/* RSI Parameters (conditionally shown) */}
      {strategy === 'rsi' && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">RSI Oversold</label>
            <input
              type="number"
              value={rsiOversold}
              onChange={(e) => setRsiOversold(Number(e.target.value))}
              min={0}
              max={100}
              className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">RSI Overbought</label>
            <input
              type="number"
              value={rsiOverbought}
              onChange={(e) => setRsiOverbought(Number(e.target.value))}
              min={0}
              max={100}
              className="w-full bg-[#0f0f1e] text-zinc-100 px-2 py-1 text-sm rounded border border-zinc-700 focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="mb-3 p-2 bg-red-900/30 border border-red-700 rounded text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Run Button */}
      <button
        onClick={handleRun}
        disabled={running}
        className={`w-full py-2 rounded font-medium text-sm transition-colors ${
          running
            ? 'bg-zinc-700 text-zinc-400 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-700 text-white'
        }`}
      >
        {running ? 'Running Backtest...' : 'Run Backtest'}
      </button>

      {/* Strategy Info */}
      {strategies.length > 0 && (
        <div className="mt-3 p-2 bg-[#0f0f1e] rounded border border-zinc-700">
          <div className="text-xs text-zinc-400">
            {strategies.find((s) => s.name === strategy)?.description || ''}
          </div>
        </div>
      )}
    </div>
  )
}
