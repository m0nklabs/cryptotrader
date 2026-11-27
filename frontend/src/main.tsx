import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import './index.css'

const queryClient = new QueryClient()

/**
 * Last-resort fallback: if the application shell itself throws (sidebar,
 * header, providers), the operator still sees what happened and can reload
 * instead of staring at a blank page.
 */
function renderAppCrashFallback(error: Error, retry: () => void) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-root)] p-6 text-[var(--text)]">
      <div className="max-w-md rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-6 text-center">
        <div className="text-sm font-semibold text-[var(--danger)]">The dashboard failed to start</div>
        <div className="mt-1 text-xs text-[var(--muted)]">
          A rendering error took down the dashboard shell. Reload the page; if it keeps happening,
          check the backend health endpoint and the browser console for the stack trace.
        </div>
        <div className="mt-3 truncate font-mono text-[11px] text-[var(--faint)]" title={error.message}>
          {error.message}
        </div>
        <div className="mt-4 flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={retry}
            className="rounded-[var(--radius-sm)] border border-[var(--line-strong)] bg-[var(--panel-2)] px-3 py-1 text-xs font-medium text-[var(--text)] hover:bg-[var(--elevated)]"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-[var(--radius-sm)] border border-[var(--line-strong)] bg-[var(--panel-2)] px-3 py-1 text-xs font-medium text-[var(--text)] hover:bg-[var(--elevated)]"
          >
            Reload page
          </button>
        </div>
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary fallback={renderAppCrashFallback}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
