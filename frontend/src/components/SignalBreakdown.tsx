/**
 * Signal Breakdown Component
 * ==========================
 * Shows detailed breakdown of signal contributors
 */

import type { SignalDetail } from '../api/signals'

type Props = {
  signals: SignalDetail[]
  isExpanded: boolean
  onToggle: () => void
}

export default function SignalBreakdown({ signals, isExpanded, onToggle }: Props) {
  if (signals.length === 0) {
    return (
      <div className="text-xs text-gray-500">
        No signal breakdown available
      </div>
    )
  }

  return (
    <div className="mt-2">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between rounded px-2 py-1 text-xs text-gray-400 hover:bg-gray-800"
      >
        <span>Signal Breakdown ({signals.length} indicators)</span>
        <span>{isExpanded ? '▼' : '▶'}</span>
      </button>

      {isExpanded && (
        <div className="mt-2 space-y-1 rounded border border-gray-800 bg-gray-900/50 p-2">
          {signals.map((signal, idx) => {
            const sideColor =
              signal.side === 'BUY'
                ? 'text-green-500'
                : signal.side === 'SELL'
                  ? 'text-red-500'
                  : 'text-gray-500'

            const strengthBars = Math.round((signal.strength / 100) * 5)

            return (
              <div key={idx} className="flex flex-col gap-1 rounded border border-gray-800 bg-gray-900 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-300">{signal.code}</span>
                  <span className={`text-xs font-medium ${sideColor}`}>{signal.side}</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex gap-0.5">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <div
                        key={i}
                        className={`h-2 w-4 rounded-sm ${
                          i < strengthBars ? 'bg-blue-500' : 'bg-gray-700'
                        }`}
                      />
                    ))}
                  </div>
                  <span className="text-xs text-gray-500">{signal.strength}%</span>
                </div>

                {signal.value && (
                  <div className="text-xs text-gray-400">
                    Value: <span className="text-gray-300">{signal.value}</span>
                  </div>
                )}

                <div className="text-xs text-gray-500">{signal.reason}</div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
