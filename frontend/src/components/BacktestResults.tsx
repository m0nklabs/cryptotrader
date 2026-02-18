/**
 * Backtest Results Component
 * ===========================
 * Display backtest performance metrics and trade history
 */

import type { BacktestResult } from '../api/backtest'

type Props = {
  results: BacktestResult
}

export default function BacktestResults({ results }: Props) {
  // Format currency
  const fmt = (val: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val)
  }

  // Format percentage
  const pct = (val: number) => {
    return `${(val * 100).toFixed(2)}%`
  }

  // Determine color based on value
  const colorClass = (val: number) => {
    if (val > 0) return 'text-green-400'
    if (val < 0) return 'text-red-400'
    return 'text-zinc-400'
  }

  const winningTrades = results.trades.filter((t) => parseFloat(t.pnl) > 0)
  const losingTrades = results.trades.filter((t) => parseFloat(t.pnl) < 0)

  return (
    <div className="bg-[#1a1a2e] p-4 rounded border border-zinc-700">
      <h2 className="text-lg font-semibold mb-4 text-zinc-100">Backtest Results</h2>

      {/* Summary Header */}
      <div className="mb-4 p-3 bg-[#0f0f1e] rounded border border-zinc-700">
        <div className="text-xs text-zinc-400 mb-1">
          {results.exchange} {results.symbol} ({results.timeframe}) - {results.strategy.toUpperCase()}
        </div>
        <div className="text-xs text-zinc-500">
          {new Date(results.start_date).toLocaleDateString()} - {new Date(results.end_date).toLocaleDateString()}
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {/* Total P&L */}
        <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
          <div className="text-xs text-zinc-400 mb-1">Total P&L</div>
          <div className={`text-lg font-semibold ${colorClass(results.total_pnl)}`}>
            {fmt(results.total_pnl)}
          </div>
        </div>

        {/* Total Return */}
        <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
          <div className="text-xs text-zinc-400 mb-1">Total Return</div>
          <div className={`text-lg font-semibold ${colorClass(results.total_return)}`}>
            {pct(results.total_return)}
          </div>
        </div>

        {/* Sharpe Ratio */}
        <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
          <div className="text-xs text-zinc-400 mb-1">Sharpe Ratio</div>
          <div className={`text-lg font-semibold ${colorClass(results.sharpe_ratio)}`}>
            {results.sharpe_ratio.toFixed(2)}
          </div>
        </div>

        {/* Max Drawdown */}
        <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
          <div className="text-xs text-zinc-400 mb-1">Max Drawdown</div>
          <div className="text-lg font-semibold text-red-400">
            {pct(results.max_drawdown)}
          </div>
        </div>

        {/* Win Rate */}
        <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
          <div className="text-xs text-zinc-400 mb-1">Win Rate</div>
          <div className={`text-lg font-semibold ${colorClass(results.win_rate - 0.5)}`}>
            {pct(results.win_rate)}
          </div>
        </div>

        {/* Profit Factor */}
        <div className="bg-[#0f0f1e] p-3 rounded border border-zinc-700">
          <div className="text-xs text-zinc-400 mb-1">Profit Factor</div>
          <div className={`text-lg font-semibold ${colorClass(results.profit_factor - 1)}`}>
            {results.profit_factor === Infinity ? '∞' : results.profit_factor.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Trade Statistics */}
      <div className="mb-4 p-3 bg-[#0f0f1e] rounded border border-zinc-700">
        <div className="text-sm font-medium text-zinc-300 mb-2">Trade Statistics</div>
        <div className="grid grid-cols-4 gap-2 text-xs">
          <div>
            <div className="text-zinc-400">Total Trades</div>
            <div className="text-zinc-100 font-medium">{results.num_trades}</div>
          </div>
          <div>
            <div className="text-zinc-400">Winners</div>
            <div className="text-green-400 font-medium">{winningTrades.length}</div>
          </div>
          <div>
            <div className="text-zinc-400">Losers</div>
            <div className="text-red-400 font-medium">{losingTrades.length}</div>
          </div>
          <div>
            <div className="text-zinc-400">Final Equity</div>
            <div className="text-zinc-100 font-medium">
              {fmt(results.equity_curve[results.equity_curve.length - 1])}
            </div>
          </div>
        </div>
      </div>

      {/* Trade History */}
      {results.trades.length > 0 && (
        <div>
          <div className="text-sm font-medium text-zinc-300 mb-2">Trade History</div>
          <div className="bg-[#0f0f1e] rounded border border-zinc-700 max-h-64 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#0f0f1e] border-b border-zinc-700">
                <tr className="text-zinc-400">
                  <th className="text-left p-2">#</th>
                  <th className="text-left p-2">Side</th>
                  <th className="text-right p-2">Entry</th>
                  <th className="text-right p-2">Exit</th>
                  <th className="text-right p-2">Size</th>
                  <th className="text-right p-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {results.trades.map((trade, idx) => {
                  const pnl = parseFloat(trade.pnl)
                  return (
                    <tr key={idx} className="border-b border-zinc-800 hover:bg-[#1a1a2e]">
                      <td className="p-2 text-zinc-400">{idx + 1}</td>
                      <td className="p-2">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-medium ${
                            trade.side === 'BUY'
                              ? 'bg-green-900/30 text-green-400'
                              : 'bg-red-900/30 text-red-400'
                          }`}
                        >
                          {trade.side}
                        </span>
                      </td>
                      <td className="p-2 text-right text-zinc-300">${trade.entry_price}</td>
                      <td className="p-2 text-right text-zinc-300">${trade.exit_price}</td>
                      <td className="p-2 text-right text-zinc-300">{trade.size}</td>
                      <td className={`p-2 text-right font-medium ${colorClass(pnl)}`}>
                        {fmt(pnl)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {results.trades.length === 0 && (
        <div className="p-4 text-center text-zinc-400 text-sm">
          No trades executed in this backtest period
        </div>
      )}
    </div>
  )
}
