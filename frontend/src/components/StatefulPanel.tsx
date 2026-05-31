/**
 * StatefulPanel — Reusable wrapper that renders loading, empty,
 * filtered-empty, error, and backend-unavailable states.
 *
 * Usage:
 *   <StatefulPanel
 *     isLoading={...}
 *     data={items}
 *     filterPredicate={(item) => item.visible}
 *     emptyMessage="No data"
 *     filteredEmptyMessage="No matches"
 *     backendUnavailableMessage="Backend offline"
 *     error={errorString}
 *     renderEmpty={() => <EmptyState />}
 *     renderFilteredEmpty={() => <FilteredEmpty />}
 *     renderBackendUnavailable={() => <BackendUnavailable />}
 *   >
 *     {items.map(item => <Item key={item.id} item={item} />)}
 *   </StatefulPanel>
 */

import React, { type ReactNode } from 'react'

type Props = {
  isLoading?: boolean
  data?: unknown[] | null
  filterPredicate?: (item: unknown) => boolean
  emptyMessage?: string
  filteredEmptyMessage?: string
  backendUnavailableMessage?: string
  error?: string | null
  renderEmpty?: () => ReactNode
  renderFilteredEmpty?: () => ReactNode
  renderBackendUnavailable?: () => ReactNode
  children: ReactNode
  className?: string
}

const DEFAULT_EMPTY_MSG = 'No data available'
const DEFAULT_FILTERED_MSG = 'No items match the current filter'
const DEFAULT_BACKEND_MSG = 'Backend unavailable — will retry automatically'

export function StatefulPanel({
  isLoading = false,
  data = null,
  filterPredicate,
  emptyMessage = DEFAULT_EMPTY_MSG,
  filteredEmptyMessage = DEFAULT_FILTERED_MSG,
  backendUnavailableMessage = DEFAULT_BACKEND_MSG,
  error,
  renderEmpty,
  renderFilteredEmpty,
  renderBackendUnavailable,
  children,
  className = '',
}: Props) {
  // Error takes highest priority
  if (error) {
    return (
      <div className={`flex flex-col items-center justify-center gap-2 p-6 ${className}`}>
        <div className="text-xs font-medium text-red-400">Error</div>
        <div className="max-w-xs text-[11px] text-gray-500 text-center" title={error}>
          {error}
        </div>
      </div>
    )
  }

  // Loading state
  if (isLoading) {
    return (
      <div className={`flex items-center justify-center p-6 ${className}`}>
        <div className="flex items-center gap-2 text-zinc-400">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="text-xs">Loading...</span>
        </div>
      </div>
    )
  }

  // Determine if data is empty
  const items = data ?? []
  const isEmpty = items.length === 0
  const isFilteredEmpty = filterPredicate ? items.every((item) => !filterPredicate(item)) : false

  // Backend unavailable check (data is null meaning fetch hasn't succeeded yet)
  if (data === null) {
    return renderBackendUnavailable?.() ?? (
      <div className={`flex flex-col items-center justify-center gap-2 p-6 ${className}`}>
        <div className="text-xs font-medium text-yellow-500">{backendUnavailableMessage}</div>
      </div>
    )
  }

  if (isEmpty) {
    return renderEmpty?.() ?? (
      <div className={`flex flex-col items-center justify-center gap-2 p-6 ${className}`}>
        <div className="text-xs text-gray-500">{emptyMessage}</div>
      </div>
    )
  }

  if (isFilteredEmpty) {
    return renderFilteredEmpty?.() ?? (
      <div className={`flex flex-col items-center justify-center gap-2 p-6 ${className}`}>
        <div className="text-xs text-gray-500">{filteredEmptyMessage}</div>
      </div>
    )
  }

  return <>{children}</>
}

export default StatefulPanel
