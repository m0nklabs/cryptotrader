/**
 * BackendUnavailable — Visual indicator for when the backend is unreachable.
 *
 * Shows a pulsing dot + message + retry button. Used as fallback inside
 * StatefulPanel when the backend hasn't responded yet or has gone offline.
 */

import React, { useState } from 'react'

type Props = {
  message?: string
  onRetry?: () => void
  className?: string
}

export function BackendUnavailable({
  message = 'Backend offline — will retry automatically',
  onRetry,
  className = '',
}: Props) {
  const [retried, setRetried] = useState(false)

  const handleRetry = () => {
    setRetried(true)
    onRetry?.()
  }

  return (
    <div className={`flex flex-col items-center justify-center gap-2 p-6 ${className}`}>
      <div className="relative">
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-3 w-3 bg-yellow-500" />
        </span>
      </div>
      <div className="text-xs font-medium text-yellow-500">{message}</div>
      {onRetry && (
        <button
          onClick={handleRetry}
          className="mt-1 rounded border border-yellow-600/50 bg-yellow-900/20 px-3 py-1 text-[11px] text-yellow-300 hover:bg-yellow-900/40"
        >
          {retried ? 'Retrying...' : 'Retry now'}
        </button>
      )}
    </div>
  )
}

export default BackendUnavailable
