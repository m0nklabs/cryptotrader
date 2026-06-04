/**
 * Trade History - Complete audit of all trades
 */

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listTrades, getOrderAuditLog, Trade, OrderAuditLog } from '../api/tradeHistory';

type ViewMode = 'trades' | 'audit';

export function TradeHistory() {
  const [viewMode, setViewMode] = useState<ViewMode>('trades');
  const [symbolFilter, setSymbolFilter] = useState('');

  const { data: tradesData, isLoading: tradesLoading } = useQuery({
    queryKey: ['trades', symbolFilter],
    queryFn: () => listTrades({ symbol: symbolFilter || undefined, limit: 100 }),
    enabled: viewMode === 'trades',
    refetchInterval: 30000,
  });

  const { data: auditData, isLoading: auditLoading } = useQuery({
    queryKey: ['audit', symbolFilter],
    queryFn: () => getOrderAuditLog({ symbol: symbolFilter || undefined, limit: 100 }),
    enabled: viewMode === 'audit',
    refetchInterval: 30000,
  });

  const trades = tradesData || [];
  const auditLogs = auditData || [];

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f] text-zinc-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-800">
        <h1 className="text-xl font-bold mb-3">Trade History</h1>
        <div className="flex items-center space-x-4">
          {/* View mode selector */}
          <div className="flex space-x-2">
            <button
              onClick={() => setViewMode('trades')}
              className={`px-3 py-1 text-xs rounded ${
                viewMode === 'trades'
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
              }`}
            >
              Executed Trades
            </button>
            <button
              onClick={() => setViewMode('audit')}
              className={`px-3 py-1 text-xs rounded ${
                viewMode === 'audit'
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
              }`}
            >
              Order Audit Log
            </button>
          </div>

          {/* Symbol filter */}
          <div className="flex-1">
            <input
              type="text"
              placeholder="Filter by symbol..."
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              className="w-full max-w-xs bg-zinc-900 border border-zinc-700 rounded px-3 py-1 text-xs focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {viewMode === 'trades' && (
          <>
            {tradesLoading ? (
              <div className="p-8 text-center text-zinc-500">Loading trades...</div>
            ) : trades.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">No trades found</div>
            ) : (
              <table className="w-full text-xs">
                <thead className="bg-zinc-900 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left text-zinc-400">Time</th>
                    <th className="px-4 py-2 text-left text-zinc-400">Symbol</th>
                    <th className="px-4 py-2 text-left text-zinc-400">Exchange</th>
                    <th className="px-4 py-2 text-center text-zinc-400">Side</th>
                    <th className="px-4 py-2 text-right text-zinc-400">Quantity</th>
                    <th className="px-4 py-2 text-right text-zinc-400">Price</th>
                    <th className="px-4 py-2 text-right text-zinc-400">Total</th>
                    <th className="px-4 py-2 text-right text-zinc-400">Fee</th>
                    <th className="px-4 py-2 text-center text-zinc-400">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade: Trade) => {
                    const isBuy = trade.side.toUpperCase() === 'BUY';
                    return (
                      <tr key={trade.id} className="border-b border-zinc-800 hover:bg-zinc-900">
                        <td className="px-4 py-3 text-zinc-500">
                          {new Date(trade.execution_time).toLocaleString()}
                        </td>
                        <td className="px-4 py-3 font-mono font-bold">{trade.symbol}</td>
                        <td className="px-4 py-3 text-zinc-400">{trade.exchange}</td>
                        <td className={`px-4 py-3 text-center font-bold ${
                          isBuy ? 'text-green-400' : 'text-red-400'
                        }`}>
                          {trade.side}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">{trade.quantity}</td>
                        <td className="px-4 py-3 text-right font-mono">${trade.price}</td>
                        <td className="px-4 py-3 text-right font-mono">${trade.quote_qty}</td>
                        <td className="px-4 py-3 text-right font-mono text-zinc-500">
                          ${trade.fee}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className="px-2 py-1 bg-zinc-800 rounded text-zinc-400">
                            {trade.trade_type}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        )}

        {viewMode === 'audit' && (
          <>
            {auditLoading ? (
              <div className="p-8 text-center text-zinc-500">Loading audit log...</div>
            ) : auditLogs.length === 0 ? (
              <div className="p-8 text-center text-zinc-500">No audit events found</div>
            ) : (
              <table className="w-full text-xs">
                <thead className="bg-zinc-900 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left text-zinc-400">Time</th>
                    <th className="px-4 py-2 text-left text-zinc-400">Order ID</th>
                    <th className="px-4 py-2 text-left text-zinc-400">Symbol</th>
                    <th className="px-4 py-2 text-center text-zinc-400">Event</th>
                    <th className="px-4 py-2 text-center text-zinc-400">Status</th>
                    <th className="px-4 py-2 text-right text-zinc-400">Filled</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((log: OrderAuditLog) => (
                    <tr key={log.id} className="border-b border-zinc-800 hover:bg-zinc-900">
                      <td className="px-4 py-3 text-zinc-500">
                        {new Date(log.event_time).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-zinc-400">{log.order_id}</td>
                      <td className="px-4 py-3 font-mono font-bold">{log.symbol}</td>
                      <td className="px-4 py-3 text-center">
                        <span className="px-2 py-1 bg-zinc-800 rounded text-blue-400">
                          {log.event_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className="px-2 py-1 bg-zinc-800 rounded text-zinc-400">
                          {log.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {log.filled_quantity || '-'} / {log.quantity || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  );
}
