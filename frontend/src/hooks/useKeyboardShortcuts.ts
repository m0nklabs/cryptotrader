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

      // Check all shortcuts for a match
      for (const shortcut of DEFAULT_SHORTCUTS) {
        if (matchesShortcut(event, shortcut)) {
          event.preventDefault()
          handler(shortcut.action)
          break
        }
      }
    },
    [handler]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [handleKeyDown])
}
