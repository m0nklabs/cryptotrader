import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../App'

describe('App Component', () => {
  it('renders the application title', () => {
    render(<App />)
    expect(screen.getByText('cryptotrader')).toBeDefined()
  })

  it('renders dashboard text', () => {
    render(<App />)
    expect(screen.getByText('dashboard')).toBeDefined()
  })

  it('renders the footer with version info', () => {
    render(<App />)
    expect(screen.getByText('v2 skeleton')).toBeDefined()
  })

  it('renders the footer with paper-trading info', () => {
    render(<App />)
    expect(screen.getByText('paper-trading default')).toBeDefined()
  })

  it('renders Market Watch panel', () => {
    render(<App />)
    expect(screen.getByText('Market Watch')).toBeDefined()
  })

  it('renders Chart panel', () => {
    render(<App />)
    expect(screen.getByText('Chart')).toBeDefined()
  })

  it('renders Opportunities panel', () => {
    render(<App />)
    expect(screen.getByText('Opportunities')).toBeDefined()
  })

  it('renders settings button', () => {
    render(<App />)
    const settingsButton = screen.getByRole('button', { name: /Settings/i })
    expect(settingsButton).toBeDefined()
  })
})
