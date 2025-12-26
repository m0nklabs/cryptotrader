/**
 * Correlation Matrix Heatmap
 * ==========================
 * Visual heatmap showing correlation between crypto assets
 */

import { useState } from 'react'
import { useCorrelation } from '../hooks/useCorrelation'
import { getCorrelationColor, formatCorrelation } from '../lib/colors'

type Props = {
  symbols: string[]
  exchange?: string
  onSymbolClick?: (symbol: string) => void
}

export default function CorrelationMatrix({
  symbols,
  exchange = 'bitfinex',
  onSymbolClick,
}: Props) {
  const [lookbackDays, setLookbackDays] = useState(30)
  const { data, loading, error } = useCorrelation(symbols, exchange, '1d', lookbackDays)

  if (symbols.length < 2) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
        Select at least 2 symbols to view correlation
      </div>
    )
  }

  if (loading) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
        Calculating correlations...
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded border border-red-800 bg-red-900/20 p-4 text-center text-sm text-red-400">
        {error}
      </div>
    )
  }

  if (!data || !data.matrix || data.matrix.length === 0) {
    return (
      <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-sm text-gray-400">
        No correlation data available
      </div>
    )
  }

  const handleCellClick = (symbol: string) => {
    if (onSymbolClick) {
      onSymbolClick(symbol)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Controls */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-1">
          <span className="text-xs text-gray-400">Lookback:</span>
          {[7, 30, 90, 365].map((days) => (
            <button
              key={days}
              onClick={() => setLookbackDays(days)}
              className={`rounded px-2 py-1 text-xs transition-colors ${
                lookbackDays === days
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {days}d
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-500">
          {data.data_points} data points
        </span>
      </div>

      {/* Matrix */}
      <div className="overflow-auto rounded border border-gray-800">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-gray-900 p-2"></th>
              {data.symbols.map((symbol) => (
                <th
                  key={symbol}
                  className="cursor-pointer bg-gray-900 p-2 text-center font-semibold text-gray-300 hover:bg-gray-800"
                  onClick={() => handleCellClick(symbol)}
                >
                  {symbol}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.symbols.map((rowSymbol, rowIdx) => (
              <tr key={rowSymbol}>
                <th
                  className="sticky left-0 cursor-pointer bg-gray-900 p-2 text-left font-semibold text-gray-300 hover:bg-gray-800"
                  onClick={() => handleCellClick(rowSymbol)}
                >
                  {rowSymbol}
                </th>
                {data.symbols.map((colSymbol, colIdx) => {
                  const value = data.matrix[rowIdx][colIdx]
                  const color = getCorrelationColor(value)
                  const isDiagonal = rowIdx === colIdx

                  return (
                    <td
                      key={`${rowSymbol}-${colSymbol}`}
                      className="p-2 text-center"
                      style={{
                        backgroundColor: isDiagonal ? '#374151' : color + '40', // Add transparency
                      }}
                      title={`${rowSymbol} vs ${colSymbol}: ${formatCorrelation(value)}`}
                    >
                      <span
                        className={
                          isDiagonal
                            ? 'font-bold text-gray-400'
                            : value >= 0.7
                              ? 'font-semibold text-green-300'
                              : value <= -0.7
                                ? 'font-semibold text-red-300'
                                : 'text-gray-300'
                        }
                      >
                        {formatCorrelation(value)}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="text-gray-400">Correlation:</span>
          <div className="flex items-center gap-1">
            <div className="h-4 w-8" style={{ backgroundColor: getCorrelationColor(-1) }} />
            <span className="text-gray-500">-1.0</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="h-4 w-8" style={{ backgroundColor: getCorrelationColor(0) }} />
            <span className="text-gray-500">0.0</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="h-4 w-8" style={{ backgroundColor: getCorrelationColor(1) }} />
            <span className="text-gray-500">+1.0</span>
          </div>
        </div>
        {data.start_time && data.end_time && (
          <span className="text-gray-500">
            {new Date(data.start_time).toLocaleDateString()} -{' '}
            {new Date(data.end_time).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  )
}
