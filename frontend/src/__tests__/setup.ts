import { afterEach, beforeAll } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// Mock matchMedia for lightweight-charts compatibility in jsdom
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // deprecated
    removeListener: () => {}, // deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => true,
  }),
})

// Suppress known async errors from lightweight-charts in jsdom
// These errors occur during chart cleanup and don't affect test results
// Note: In development mode, consider disabling this to see all errors
beforeAll(() => {
  const originalError = console.error
  const isDevelopment = import.meta.env.DEV

  console.error = (...args: any[]) => {
    const message = args[0]?.toString() || ''
    // Only suppress lightweight-charts specific errors
    const isLightweightChartsError =
      message.includes('Value is null') &&
      (message.includes('ensureNotNull') || message.includes('PriceAxisWidget'))

    if (isLightweightChartsError && !isDevelopment) {
      return
    }
    originalError.apply(console, args)
  }
})

// Cleanup after each test
afterEach(() => {
  cleanup()
})
