import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import OrdersTable from '../components/OrdersTable'
import type { Order } from '../api/trading'

function order(overrides: Partial<Order> = {}): Order {
  return {
    order_id: 1,
    mode: 'paper',
    symbol: 'BTCUSD',
    side: 'BUY',
    order_type: 'limit',
    status: 'PENDING',
    requested_qty: '1.0000',
    filled_qty: '0.0000',
    remaining_qty: '1.0000',
    fill_ratio: '0.0000',
    avg_fill_price: null,
    limit_price: null,
    fees: '0',
    slippage_bps: null,
    created_at: '2026-11-23T10:00:00+00:00',
    filled_at: null,
    ...overrides,
  }
}

const noop = async () => {}

describe('OrdersTable', () => {
  it('keeps the execution threshold of a resting limit order visible', () => {
    // A pending limit order has no fill price, so the limit price is the only
    // price an operator can inspect before the order trades.
    render(
      <OrdersTable
        orders={[order({ status: 'PENDING', limit_price: '49000' })]}
        onCancel={noop}
      />,
    )

    expect(screen.getByText('limit 49000.00')).toBeTruthy()
  })

  it('shows the average fill price and the limit price of a partial fill', () => {
    render(
      <OrdersTable
        orders={[
          order({
            status: 'PARTIAL',
            limit_price: '49000',
            avg_fill_price: '48987.5',
            filled_qty: '0.4000',
            remaining_qty: '0.6000',
            fill_ratio: '0.4000',
          }),
        ]}
        onCancel={noop}
      />,
    )

    expect(screen.getByText('48987.50')).toBeTruthy()
    expect(screen.getByText('limit 49000.00')).toBeTruthy()
    expect(screen.getByText('40%')).toBeTruthy()
  })

  it('renders no limit line for a market order that never had one', () => {
    render(
      <OrdersTable
        orders={[
          order({
            order_type: 'market',
            status: 'FILLED',
            avg_fill_price: '50000',
            filled_qty: '1.0000',
            remaining_qty: '0.0000',
            fill_ratio: '1.0000',
            filled_at: '2026-11-23T10:01:00+00:00',
          }),
        ]}
        onCancel={noop}
      />,
    )

    expect(screen.queryByText(/^limit /)).toBeNull()
  })

  it('offers cancellation only for a pending order', () => {
    const onCancel = vi.fn(async () => {})
    const { rerender } = render(
      <OrdersTable orders={[order({ status: 'PENDING' })]} onCancel={onCancel} />,
    )
    expect(screen.getAllByRole('button')).toHaveLength(1)

    rerender(
      <OrdersTable
        orders={[order({ status: 'FILLED', avg_fill_price: '50000' })]}
        onCancel={onCancel}
      />,
    )
    expect(screen.queryByRole('button')).toBeNull()
  })
})
