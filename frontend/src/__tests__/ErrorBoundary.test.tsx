import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'

import ErrorBoundary from '../components/ErrorBoundary'
import { ViewErrorFallback } from '../components/ViewErrorFallback'
import { VIEW_IDS, type ViewId } from '../nav'

/**
 * These tests pin the contract the dashboard relies on after #170:
 * a view that throws during render degrades to the fallback instead of
 * propagating and blanking the app, retry recovers once the cause is gone,
 * and switching views clears a latched error because App.tsx keys the
 * boundary on the active view id.
 */

const fallback = (error: Error, retry: () => void) => (
  <ViewErrorFallback viewId={VIEW_IDS.DASHBOARD} error={error} onRetry={retry} />
)

function ThrowingView(): ReactElement {
  throw new Error('view exploded')
}

function DashboardShell({ activeView }: { activeView: ViewId }) {
  return (
    <ErrorBoundary
      key={activeView}
      fallback={(error, retry) => (
        <ViewErrorFallback viewId={activeView} error={error} onRetry={retry} />
      )}
    >
      {activeView === VIEW_IDS.DASHBOARD ? (
        <div>healthy view content</div>
      ) : (
        <ThrowingView />
      )}
    </ErrorBoundary>
  )
}

describe('ErrorBoundary view wiring', () => {
  beforeEach(() => {
    // React and the boundary both report caught render errors; keep test output readable.
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the fallback instead of propagating a render error', () => {
    render(
      <ErrorBoundary fallback={fallback}>
        <ThrowingView />
      </ErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('This view failed to render')).toBeInTheDocument()
    expect(screen.getByText('view exploded')).toBeInTheDocument()
  })

  it('recovers after retry once the render error is gone', async () => {
    const user = userEvent.setup()
    let shouldThrow = true

    function FlakyView() {
      if (shouldThrow) throw new Error('transient render failure')
      return <div>recovered content</div>
    }

    render(
      <ErrorBoundary fallback={fallback}>
        <FlakyView />
      </ErrorBoundary>,
    )
    expect(screen.getByText('This view failed to render')).toBeInTheDocument()

    shouldThrow = false
    await user.click(screen.getByRole('button', { name: 'Retry this view' }))

    expect(await screen.findByText('recovered content')).toBeInTheDocument()
    expect(screen.queryByText('This view failed to render')).not.toBeInTheDocument()
  })

  it('clears a latched error when the active view changes (boundary key)', () => {
    const { rerender } = render(<DashboardShell activeView={VIEW_IDS.CHART} />)
    expect(screen.getByText('This view failed to render')).toBeInTheDocument()

    rerender(<DashboardShell activeView={VIEW_IDS.DASHBOARD} />)

    expect(screen.getByText('healthy view content')).toBeInTheDocument()
    expect(screen.queryByText('This view failed to render')).not.toBeInTheDocument()
  })
})
