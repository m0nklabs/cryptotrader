import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { AppCrashFallback } from './components/AppCrashFallback'
import './index.css'

const queryClient = new QueryClient()

/**
 * Last-resort fallback: if the application shell itself throws (sidebar,
 * header, providers), the operator still sees what happened and can reload
 * instead of staring at a blank page.
 */
const appCrashFallback = (error: Error, retry: () => void) => (
  <AppCrashFallback error={error} onRetry={retry} />
)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary fallback={appCrashFallback}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
