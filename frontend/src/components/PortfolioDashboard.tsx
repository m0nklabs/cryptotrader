/**
 * Portfolio Dashboard - Main portfolio tracking view
 *
 * Displays:
 * - Total equity and P&L
 * - Current positions with unrealized P&L
 * - Performance chart over time
 * - Allocation breakdown
 */

import React from 'react';
import { useLatestPortfolioSnapshot, usePortfolioSnapshots } from '../hooks/usePortfolio';
import { usePortfolioStore } from '../stores/portfolioStore';
import { listPositions, Position } from '../api/trading';
import { useQuery } from '@tanstack/react-query';

export function PortfolioDashboard() {
  const { data: latestSnapshot, isLoading: snapshotLoading } = useLatestPortfolioSnapshot();
  const { timeRange, setTimeRange } = usePortfolioStore();

  // Fetch current positions
  const { data: positionsData, isLoading: positionsLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: listPositions,
    refetchInterval: 10000,
  });

  const positions = positionsData || [];

  if (snapshotLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-zinc-400">Loading portfolio...</div>
      </div>
    );
  }

  const equity = latestSnapshot ? parseFloat(latestSnapshot.total_equity) : 0;
  const totalPnL = latestSnapshot ? parseFloat(latestSnapshot.total_pnl) : 0;
  const unrealizedPnL = latestSnapshot ? parseFloat(latestSnapshot.unrealized_pnl) : 0;
  const realizedPnL = latestSnapshot ? parseFloat(latestSnapshot.realized_pnl) : 0;
  const pnlPercentage = equity > 0 ? (totalPnL / equity) * 100 : 0;

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f] text-zinc-200 overflow-y-auto p-4 space-y-4">
      {/* Header with summary stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <div className="text-xs text-zinc-400 mb-1">Total Equity</div>
          <div className="text-2xl font-bold">
            ${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-zinc-500 mt-1">
            {latestSnapshot?.quote_currency || 'USDT'}
          </div>
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <div className="text-xs text-zinc-400 mb-1">Total P&L</div>
          <div className={`text-2xl font-bold ${totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {totalPnL >= 0 ? '+' : ''}${totalPnL.toFixed(2)}
          </div>
          <div className={`text-xs mt-1 ${pnlPercentage >= 0 ? 'text-green-500' : 'text-red-500'}`}>
            {pnlPercentage >= 0 ? '+' : ''}{pnlPercentage.toFixed(2)}%
          </div>
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <div className="text-xs text-zinc-400 mb-1">Unrealized P&L</div>
          <div className={`text-2xl font-bold ${unrealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {unrealizedPnL >= 0 ? '+' : ''}${unrealizedPnL.toFixed(2)}
          </div>
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-zinc-800">
          <div className="text-xs text-zinc-400 mb-1">Realized P&L</div>
          <div className={`text-2xl font-bold ${realizedPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {realizedPnL >= 0 ? '+' : ''}${realizedPnL.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Time range selector */}
      <div className="flex items-center space-x-2">
        <span className="text-xs text-zinc-400">Time Range:</span>
        {(['1D', '1W', '1M', '3M', '1Y', 'ALL'] as const).map((range) => (
          <button
            key={range}
            onClick={() => setTimeRange(range)}
            className={`px-3 py-1 text-xs rounded ${
              timeRange === range
                ? 'bg-blue-600 text-white'
                : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
            }`}
          >
            {range}
          </button>
        ))}
      </div>

      {/* Positions table */}
      <div className="bg-[#1a1a2e] rounded-lg border border-zinc-800 flex-1 overflow-hidden flex flex-col">
        <div className="px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-semibold">Open Positions ({positions.length})</h2>
        </div>
        <div className="overflow-y-auto">
          {positionsLoading ? (
            <div className="p-4 text-center text-zinc-500">Loading positions...</div>
          ) : positions.length === 0 ? (
            <div className="p-4 text-center text-zinc-500">No open positions</div>
          ) : (
            <table className="w-full text-xs">
              <thead className="bg-zinc-900 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left text-zinc-400">Symbol</th>
                  <th className="px-4 py-2 text-right text-zinc-400">Quantity</th>
                  <th className="px-4 py-2 text-right text-zinc-400">Avg Entry</th>
                  <th className="px-4 py-2 text-right text-zinc-400">Current Price</th>
                  <th className="px-4 py-2 text-right text-zinc-400">Unrealized P&L</th>
                  <th className="px-4 py-2 text-right text-zinc-400">Realized P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position: Position, index: number) => {
                  const unrealizedPnL = parseFloat(position.unrealized_pnl);
                  const realizedPnL = parseFloat(position.realized_pnl);
                  const value = parseFloat(position.qty) * parseFloat(position.current_price);

                  return (
                    <tr key={index} className="border-b border-zinc-800 hover:bg-zinc-900">
                      <td className="px-4 py-3 font-mono">{position.symbol}</td>
                      <td className="px-4 py-3 text-right font-mono">{position.qty}</td>
                      <td className="px-4 py-3 text-right font-mono">${position.avg_entry}</td>
                      <td className="px-4 py-3 text-right font-mono">${position.current_price}</td>
                      <td className={`px-4 py-3 text-right font-mono ${
                        unrealizedPnL >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {unrealizedPnL >= 0 ? '+' : ''}${unrealizedPnL.toFixed(2)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono ${
                        realizedPnL >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {realizedPnL >= 0 ? '+' : ''}${realizedPnL.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
