/**
 * Shortcut Store
 * ==============
 * Manages custom keyboard shortcut bindings
 */

import { create } from 'zustand'
import { DEFAULT_SHORTCUTS, type ShortcutDefinition, type ShortcutAction } from '../lib/shortcuts'

type ShortcutState = {
  shortcuts: ShortcutDefinition[]
  customBindings: Partial<Record<ShortcutAction, string>>

  // Actions
  setCustomBinding: (action: ShortcutAction, key: string) => void
  resetToDefaults: () => void
  loadFromStorage: () => void
  saveToStorage: () => void
}

const STORAGE_KEY = 'keyboard-shortcuts'

export const useShortcutStore = create<ShortcutState>((set, get) => ({
  shortcuts: DEFAULT_SHORTCUTS,
  customBindings: {},

  setCustomBinding: (action, key) => {
    set((state) => ({
      customBindings: {
        ...state.customBindings,
        [action]: key,
      },
    }))
    get().saveToStorage()
  },

  resetToDefaults: () => {
    set({ customBindings: {} })
    localStorage.removeItem(STORAGE_KEY)
  },

  loadFromStorage: () => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const bindings = JSON.parse(saved)
        set({ customBindings: bindings })
      }
    } catch (err) {
      console.error('Failed to load keyboard shortcuts:', err)
    }
  },

  saveToStorage: () => {
    try {
      const { customBindings } = get()
      localStorage.setItem(STORAGE_KEY, JSON.stringify(customBindings))
    } catch (err) {
      console.error('Failed to save keyboard shortcuts:', err)
    }
  },
}))
