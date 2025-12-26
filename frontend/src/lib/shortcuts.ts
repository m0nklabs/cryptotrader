/**
 * Keyboard Shortcuts Definitions
 * ===============================
 * Centralized keyboard shortcut configuration
 */

export type ShortcutAction =
  | 'showHelp'
  | 'timeframe1'
  | 'timeframe2'
  | 'timeframe3'
  | 'timeframe4'
  | 'timeframe5'
  | 'timeframe6'
  | 'zoomIn'
  | 'zoomOut'
  | 'panLeft'
  | 'panRight'
  | 'jumpToLatest'
  | 'focusSearch'
  | 'closeModal'
  | 'toggleWatchlist'
  | 'toggleOrderBook'

export type ShortcutDefinition = {
  key: string
  modifiers?: ('Ctrl' | 'Shift' | 'Alt' | 'Meta')[]
  action: ShortcutAction
  description: string
  category: 'navigation' | 'chart' | 'panels' | 'general'
}

export const DEFAULT_SHORTCUTS: ShortcutDefinition[] = [
  // General
  {
    key: '?',
    action: 'showHelp',
    description: 'Show keyboard shortcuts help',
    category: 'general',
  },
  {
    key: 'Escape',
    action: 'closeModal',
    description: 'Close modal/unfocus',
    category: 'general',
  },

  // Timeframe switching
  {
    key: '1',
    action: 'timeframe1',
    description: 'Switch to 1m timeframe',
    category: 'chart',
  },
  {
    key: '2',
    action: 'timeframe2',
    description: 'Switch to 5m timeframe',
    category: 'chart',
  },
  {
    key: '3',
    action: 'timeframe3',
    description: 'Switch to 15m timeframe',
    category: 'chart',
  },
  {
    key: '4',
    action: 'timeframe4',
    description: 'Switch to 1h timeframe',
    category: 'chart',
  },
  {
    key: '5',
    action: 'timeframe5',
    description: 'Switch to 4h timeframe',
    category: 'chart',
  },
  {
    key: '6',
    action: 'timeframe6',
    description: 'Switch to 1d timeframe',
    category: 'chart',
  },

  // Chart navigation
  {
    key: '+',
    action: 'zoomIn',
    description: 'Zoom in chart',
    category: 'chart',
  },
  {
    key: '-',
    action: 'zoomOut',
    description: 'Zoom out chart',
    category: 'chart',
  },
  {
    key: 'ArrowLeft',
    action: 'panLeft',
    description: 'Pan chart left',
    category: 'chart',
  },
  {
    key: 'ArrowRight',
    action: 'panRight',
    description: 'Pan chart right',
    category: 'chart',
  },
  {
    key: 'Home',
    action: 'jumpToLatest',
    description: 'Jump to latest candle',
    category: 'chart',
  },

  // Search and panels
  {
    key: '/',
    action: 'focusSearch',
    description: 'Focus symbol search',
    category: 'navigation',
  },
  {
    key: 'w',
    action: 'toggleWatchlist',
    description: 'Toggle watchlist panel',
    category: 'panels',
  },
  {
    key: 'o',
    action: 'toggleOrderBook',
    description: 'Toggle order book panel',
    category: 'panels',
  },
]

export function formatShortcut(shortcut: ShortcutDefinition): string {
  const parts: string[] = []

  if (shortcut.modifiers) {
    parts.push(...shortcut.modifiers)
  }
  parts.push(shortcut.key)

  return parts.join('+')
}

// Keys that implicitly require shift (e.g., ? is Shift+/)
const IMPLICIT_SHIFT_KEYS = ['?', '!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '+', '_']

export function matchesShortcut(
  event: KeyboardEvent,
  shortcut: ShortcutDefinition
): boolean {
  // Check key match
  if (event.key !== shortcut.key) return false

  // Check modifiers
  const hasCtrl = event.ctrlKey || event.metaKey
  const hasShift = event.shiftKey
  const hasAlt = event.altKey

  const needsCtrl = shortcut.modifiers?.includes('Ctrl') || shortcut.modifiers?.includes('Meta') || false
  const needsShift = shortcut.modifiers?.includes('Shift') || false
  const needsAlt = shortcut.modifiers?.includes('Alt') || false

  // For special keys that implicitly require shift (like ? which is Shift+/),
  // we don't check shift modifier unless explicitly specified in the shortcut definition
  const shouldIgnoreShift = IMPLICIT_SHIFT_KEYS.includes(shortcut.key) && !needsShift

  if (needsCtrl !== hasCtrl) return false
  if (needsAlt !== hasAlt) return false
  // Only check shift if we're not ignoring it for implicit shift keys
  if (!shouldIgnoreShift && needsShift !== hasShift) return false

  return true
}
