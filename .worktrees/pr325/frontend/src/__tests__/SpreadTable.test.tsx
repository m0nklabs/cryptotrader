import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'

import SpreadTable from '../components/SpreadTable'

describe('SpreadTable', () => {
  it('renders arbitrage rows', () => {
    render(
      <SpreadTable
        opportunities={[
          {
            symbol: 'BTCUSD',
            buy_exchange: 'bitfinex',
            sell_exchange: 'binance',
            buy_price: 100,
            sell_price: 105,
            spread_pct: 5,
            net_profit: 4.28,
            net_profit_pct: 4.28,
            total_fees: 0.71,
          },
        ]}
      />
    )

    expect(screen.getByText('BTCUSD')).toBeInTheDocument()
    expect(screen.getByText('bitfinex @ $100.00')).toBeInTheDocument()
    expect(screen.getByText('binance @ $105.00')).toBeInTheDocument()
  })
})
