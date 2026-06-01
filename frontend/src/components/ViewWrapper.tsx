/**
 * ViewWrapper — Combines ErrorBoundary + StatefulPanel into a single
 * wrapper component for dashboard views.
 *
 * Provides:
 * - Error boundary catching render errors
 * - Loading / empty / filtered-empty / backend-unavailable states
 * - Optional error display overlay
 *
 * Usage:
 *   <ViewWrapper isLoading={isLoading} error={error} data={data}>
 *     {data.map(item => <Item key={item.id} />)}
 *   </ViewWrapper>
 */

import React, { type ReactNode } from 'react'
import ErrorBoundary from './ErrorBoundary'
import { StatefulPanel } from './StatefulPanel'
import { BackendUnavailable } from './BackendUnavailable'

type Props = {
  isLoading?: boolean
  error?: string | null
  data?: unknown[] | null
  filterPredicate?: (item: unknown) => boolean
  emptyMessage?: string
  filteredEmptyMessage?: string
  children: ReactNode
  className?: string
  errorBoundaryFallback?: ReactNode | ((error: Error, retry: () => void) => ReactNode)
  onRetry?: () => void
}

export function ViewWrapper({
  isLoading = false,
  error,
  data = null,
  filterPredicate,
  emptyMessage,
  filteredEmptyMessage,
  children,
  className = '',
  errorBoundaryFallback,
  onRetry,
}: Props) {
  return (
    <ErrorBoundary fallback={errorBoundaryFallback}>
      <StatefulPanel
        isLoading={isLoading}
        data={data}
        filterPredicate={filterPredicate}
        emptyMessage={emptyMessage}
        filteredEmptyMessage={filteredEmptyMessage}
        backendUnavailableMessage="Backend unavailable — will retry automatically"
        error={error}
        renderBackendUnavailable={() => (
          <BackendUnavailable onRetry={onRetry} />
        )}
        className={className}
      >
        {children}
      </StatefulPanel>
    </ErrorBoundary>
  )
}

export default ViewWrapper
