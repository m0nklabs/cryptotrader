/**
 * Visual Projections Component
 * =============================
 * Draw future price expectations/forecasts on the chart
 */

import { useState } from 'react'

export type ProjectionType = 'linear' | 'exponential' | 'fibonacci'

export type Projection = {
  id: string
  type: ProjectionType
  startTime: number
  startPrice: number
  endTime: number
  endPrice: number
  confidence: number // 0-100
  color: string
}

type Props = {
  projections: Projection[]
  onAdd?: (projection: Projection) => void
  onRemove?: (id: string) => void
  onUpdate?: (projection: Projection) => void
}

export default function VisualProjections({ projections, onAdd, onRemove, onUpdate }: Props) {
  const [showToolbar, setShowToolbar] = useState(false)

  return (
    <div className="flex flex-col gap-2">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setShowToolbar(!showToolbar)}
          className="rounded bg-gray-800 px-3 py-1 text-xs text-gray-300 hover:bg-gray-700"
        >
          {showToolbar ? 'Hide' : 'Show'} Projection Tools
        </button>
        {projections.length > 0 && (
          <span className="text-xs text-gray-500">{projections.length} projection(s)</span>
        )}
      </div>

      {showToolbar && (
        <div className="rounded border border-gray-800 bg-gray-900 p-3">
          <div className="mb-2 text-xs font-semibold text-gray-300">Add Projection</div>
          <div className="flex gap-2">
            <button
              onClick={() => {
                if (onAdd) {
                  onAdd({
                    id: `proj-${Date.now()}`,
                    type: 'linear',
                    startTime: Date.now(),
                    startPrice: 0,
                    endTime: Date.now() + 86400000, // +1 day
                    endPrice: 0,
                    confidence: 50,
                    color: '#3b82f6',
                  })
                }
              }}
              className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
            >
              Linear Trend
            </button>
            <button
              onClick={() => {
                if (onAdd) {
                  onAdd({
                    id: `proj-${Date.now()}`,
                    type: 'exponential',
                    startTime: Date.now(),
                    startPrice: 0,
                    endTime: Date.now() + 86400000,
                    endPrice: 0,
                    confidence: 50,
                    color: '#10b981',
                  })
                }
              }}
              className="rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700"
            >
              Exponential
            </button>
            <button
              onClick={() => {
                if (onAdd) {
                  onAdd({
                    id: `proj-${Date.now()}`,
                    type: 'fibonacci',
                    startTime: Date.now(),
                    startPrice: 0,
                    endTime: Date.now() + 86400000,
                    endPrice: 0,
                    confidence: 50,
                    color: '#8b5cf6',
                  })
                }
              }}
              className="rounded bg-purple-600 px-3 py-1 text-xs text-white hover:bg-purple-700"
            >
              Fibonacci Levels
            </button>
          </div>
        </div>
      )}

      {/* Projections List */}
      {projections.length > 0 && (
        <div className="space-y-1">
          {projections.map((proj) => (
            <div
              key={proj.id}
              className="flex items-center justify-between rounded border border-gray-800 bg-gray-900 p-2"
            >
              <div className="flex items-center gap-2">
                <div
                  className="h-3 w-3 rounded"
                  style={{ backgroundColor: proj.color }}
                />
                <span className="text-xs font-medium text-gray-300">
                  {proj.type.charAt(0).toUpperCase() + proj.type.slice(1)} Projection
                </span>
                <span className="text-xs text-gray-500">
                  Confidence: {proj.confidence}%
                </span>
              </div>
              <button
                onClick={() => onRemove && onRemove(proj.id)}
                className="rounded px-2 py-0.5 text-xs text-red-400 hover:bg-red-900/20"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {projections.length === 0 && !showToolbar && (
        <div className="rounded border border-gray-800 bg-gray-900 p-4 text-center text-xs text-gray-500">
          No projections. Click "Show Projection Tools" to add one.
        </div>
      )}
    </div>
  )
}
