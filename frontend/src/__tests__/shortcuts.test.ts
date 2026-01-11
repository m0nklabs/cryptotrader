/**
 * Keyboard Shortcuts Tests
 * ========================
 */

import { describe, it, expect } from 'vitest'
import { matchesShortcut, formatShortcut, DEFAULT_SHORTCUTS } from '../lib/shortcuts'

describe('Keyboard Shortcuts', () => {
  describe('matchesShortcut', () => {
    it('matches simple key without modifiers', () => {
      const shortcut = DEFAULT_SHORTCUTS.find((s) => s.key === 'Home')!
      const event = new KeyboardEvent('keydown', { key: 'Home' })
      expect(matchesShortcut(event, shortcut)).toBe(true)
    })

    it('does not match different key', () => {
      const shortcut = DEFAULT_SHORTCUTS.find((s) => s.key === '?')!
      const event = new KeyboardEvent('keydown', { key: 'a' })
      expect(matchesShortcut(event, shortcut)).toBe(false)
    })

    it('matches key with modifiers', () => {
      const shortcut = {
        key: 's',
        modifiers: ['Ctrl' as const],
        action: 'test' as any,
        description: 'Test',
        category: 'general' as const,
      }
      const event = new KeyboardEvent('keydown', { key: 's', ctrlKey: true })
      expect(matchesShortcut(event, shortcut)).toBe(true)
    })

    it('does not match when modifier missing', () => {
      const shortcut = {
        key: 's',
        modifiers: ['Ctrl' as const],
        action: 'test' as any,
        description: 'Test',
        category: 'general' as const,
      }
      const event = new KeyboardEvent('keydown', { key: 's' })
      expect(matchesShortcut(event, shortcut)).toBe(false)
    })
  })

  describe('formatShortcut', () => {
    it('formats simple shortcut', () => {
      const shortcut = DEFAULT_SHORTCUTS.find((s) => s.key === '?')!
      expect(formatShortcut(shortcut)).toBe('?')
    })

    it('formats shortcut with modifiers', () => {
      const shortcut = {
        key: 's',
        modifiers: ['Ctrl' as const, 'Shift' as const],
        action: 'test' as any,
        description: 'Test',
        category: 'general' as const,
      }
      expect(formatShortcut(shortcut)).toBe('Ctrl+Shift+s')
    })
  })

  describe('DEFAULT_SHORTCUTS', () => {
    it('has help shortcut', () => {
      const help = DEFAULT_SHORTCUTS.find((s) => s.action === 'showHelp')
      expect(help).toBeDefined()
      expect(help?.key).toBe('?')
    })

    it('has timeframe shortcuts 1-6', () => {
      for (let i = 1; i <= 6; i++) {
        const tf = DEFAULT_SHORTCUTS.find((s) => s.action === `timeframe${i}`)
        expect(tf).toBeDefined()
        expect(tf?.key).toBe(String(i))
      }
    })

    it('has chart navigation shortcuts', () => {
      expect(DEFAULT_SHORTCUTS.find((s) => s.action === 'zoomIn')).toBeDefined()
      expect(DEFAULT_SHORTCUTS.find((s) => s.action === 'zoomOut')).toBeDefined()
      expect(DEFAULT_SHORTCUTS.find((s) => s.action === 'panLeft')).toBeDefined()
      expect(DEFAULT_SHORTCUTS.find((s) => s.action === 'panRight')).toBeDefined()
    })
  })
})
