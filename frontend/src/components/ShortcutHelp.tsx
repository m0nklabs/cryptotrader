/**
 * Shortcut Help Modal
 * ===================
 * Displays keyboard shortcuts reference
 */

import { DEFAULT_SHORTCUTS, formatShortcut } from '../lib/shortcuts'
import { useEffect } from 'react'

type Props = {
  isOpen: boolean
  onClose: () => void
}

export default function ShortcutHelp({ isOpen, onClose }: Props) {
  // Handle escape key to close modal
  useEffect(() => {
    if (!isOpen) return

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const categories = {
    general: 'General',
    chart: 'Chart Navigation',
    navigation: 'Navigation',
    panels: 'Panels',
  }

  // Handle click outside to close modal
  const handleBackdropClick = () => {
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="shortcut-help-title"
    >
      <div
        className="w-full max-w-2xl rounded-lg border border-gray-800 bg-gray-900 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="shortcut-help-title" className="text-lg font-semibold text-gray-100">
            Keyboard Shortcuts
          </h2>
          <button
            onClick={onClose}
            className="rounded px-3 py-1 text-sm text-gray-400 hover:bg-gray-800 hover:text-gray-200"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="space-y-6">
          {Object.entries(categories).map(([category, label]) => {
            const shortcuts = DEFAULT_SHORTCUTS.filter((s) => s.category === category)
            if (shortcuts.length === 0) return null

            return (
              <div key={category}>
                <h3 className="mb-2 text-sm font-semibold text-gray-300">{label}</h3>
                <div className="space-y-1">
                  {shortcuts.map((shortcut) => (
                    <div
                      key={shortcut.action}
                      className="flex items-center justify-between rounded px-3 py-2 hover:bg-gray-800"
                    >
                      <span className="text-sm text-gray-400">{shortcut.description}</span>
                      <kbd className="rounded bg-gray-800 px-2 py-1 text-xs font-mono text-gray-200">
                        {formatShortcut(shortcut)}
                      </kbd>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-6 border-t border-gray-800 pt-4 text-center text-xs text-gray-500">
          Press <kbd className="rounded bg-gray-800 px-2 py-0.5 font-mono">?</kbd> to toggle this
          help, <kbd className="rounded bg-gray-800 px-2 py-0.5 font-mono">Escape</kbd> to close
        </div>
      </div>
    </div>
  )
}
