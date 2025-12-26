/**
 * Keyboard Shortcuts Hook
 * ========================
 * Global keyboard event handler for shortcuts
 */

import { useEffect, useCallback } from 'react'
import { DEFAULT_SHORTCUTS, matchesShortcut, type ShortcutAction } from '../lib/shortcuts'
import { useShortcutStore } from '../stores/shortcutStore'

type ShortcutHandler = (action: ShortcutAction) => void

export function useKeyboardShortcuts(handler: ShortcutHandler) {
  const { shortcuts, loadFromStorage } = useShortcutStore()

  // Load custom bindings on mount
  useEffect(() => {
    loadFromStorage()
  }, [loadFromStorage])

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in inputs
      const target = event.target as HTMLElement
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return
      }

      // Use custom shortcuts if available, otherwise use defaults
      const activeShortcuts = shortcuts.length > 0 ? shortcuts : DEFAULT_SHORTCUTS

      // Check all shortcuts for a match
      for (const shortcut of activeShortcuts) {
        if (matchesShortcut(event, shortcut)) {
          event.preventDefault()
          handler(shortcut.action)
          break
        }
      }
    },
    [handler, shortcuts]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [handleKeyDown])
}
