/**
 * ViewErrorFallback — the operator-facing fallback rendered by the per-view
 * ErrorBoundary in `App.tsx`.
 *
 * A render error inside one dashboard view must degrade that view only, so the
 * fallback names the failed view, keeps the error message available for a bug
 * report, and offers a retry that remounts the view. Colours come from the FLIP
 * tokens in `index.css` (`--panel`, `--line`, `--danger`, …), so light and dark
 * mode both work without hardcoded values.
 */

import type { ViewId } from '../nav'

type Props = {
  viewId: ViewId
  error: Error
  onRetry: () => void
}

export function ViewErrorFallback({ viewId, error, onRetry }: Props) {
  return (
    <div
      role="alert"
      className="mx-auto my-6 max-w-md rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] p-6 text-center"
    >
      <div className="text-sm font-semibold text-[var(--danger)]">This view failed to render</div>
      <div className="mt-1 text-xs text-[var(--muted)]">
        The view <span className="font-mono text-[var(--text)]">{viewId}</span> hit an unexpected
        error. The rest of the dashboard keeps working — switch to another view, or retry this one.
      </div>
      <div
        className="mx-auto mt-3 max-w-md truncate font-mono text-[11px] text-[var(--faint)]"
        title={error.message}
      >
        {error.message}
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-[var(--radius-sm)] border border-[var(--line-strong)] bg-[var(--panel-2)] px-3 py-1 text-xs font-medium text-[var(--text)] hover:bg-[var(--elevated)]"
      >
        Retry this view
      </button>
    </div>
  )
}

export default ViewErrorFallback
