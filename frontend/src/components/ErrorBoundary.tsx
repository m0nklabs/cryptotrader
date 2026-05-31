/**
 * ErrorBoundary — React class component that catches render errors
 * in its child component tree and logs them.
 *
 * Displays a fallback UI with error message and retry button.
 * Supports nested boundaries via `errorInfo` prop.
 */

import React, { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
  children: ReactNode
  fallback?: ReactNode | ((error: Error, retry: () => void) => ReactNode)
  onError?: (error: Error, errorInfo: ErrorInfo) => void
  fallbackClassName?: string
}

type State = {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.props.onError?.(error, errorInfo)
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  retry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError && this.state.error) {
      const fallback =
        typeof this.props.fallback === 'function'
          ? this.props.fallback(this.state.error, this.retry)
          : this.props.fallback

      if (fallback !== undefined) return <>{fallback}</>

      const cls = this.props.fallbackClassName || 'text-xs text-red-400'
      return (
        <div className={`flex flex-col items-center justify-center gap-2 p-4 ${cls}`}>
          <div className="text-sm font-medium">Something went wrong</div>
          <div className="max-w-xs truncate text-[11px] text-gray-500" title={this.state.error.message}>
            {this.state.error.message}
          </div>
          <button
            onClick={this.retry}
            className="mt-1 rounded border border-gray-600 bg-gray-800 px-3 py-1 text-[11px] hover:bg-gray-700"
          >
            Retry
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
