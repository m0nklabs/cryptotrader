/**
 * Backtest View
 * ==============
 * Main view combining backtest runner, results, and equity curve
 */

import { useState } from 'react'
import BacktestRunner from '../components/BacktestRunner'
import BacktestResults from '../components/BacktestResults'
import EquityCurve from '../components/EquityCurve'
import type { BacktestResult } from '../api/backtest'

export default function BacktestView() {
  const [results, setResults] = useState<BacktestResult | null>(null)

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold text-zinc-100">Backtesting</h1>

      {/* Configuration Panel */}
      <BacktestRunner onResultsReady={setResults} />

      {/* Results Display */}
      {results && (
        <>
          <EquityCurve
            equityCurve={results.equity_curve}
            initialCapital={results.initial_capital}
          />
          <BacktestResults results={results} />
        </>
      )}

      {/* No Results Placeholder */}
      {!results && (
        <div className="bg-[#1a1a2e] p-8 rounded border border-zinc-700 text-center">
          <div className="text-zinc-400 text-sm">
            Configure parameters above and click "Run Backtest" to see results
          </div>
        </div>
      )}
    </div>
  )
}
