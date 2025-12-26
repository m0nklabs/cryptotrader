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
beforeAll(() => {
  const originalError = console.error
  console.error = (...args: any[]) => {
    const message = args[0]?.toString() || ''
    // Ignore lightweight-charts async errors
    if (message.includes('Value is null') ||
        message.includes('ensureNotNull') ||
        message.includes('lightweight-charts')) {
      return
    }
    originalError.apply(console, args)
  }
})

// Cleanup after each test
afterEach(() => {
  cleanup()
})
