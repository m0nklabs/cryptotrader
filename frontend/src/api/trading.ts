/**
 * Paper trading API client.
 * Connects to backend endpoints for order and position management.
 */

const API_BASE = '/api';

export type OrderSide = 'BUY' | 'SELL';
export type OrderType = 'market' | 'limit';
export type OrderStatus = 'PENDING' | 'FILLED' | 'CANCELLED';

export interface Order {
  order_id: number;
  symbol: string;
  side: OrderSide;
  order_type: OrderType;
  qty: string;
  limit_price: string | null;
  fill_price: string | null;
  status: OrderStatus;
  slippage_bps: string | null;
  created_at: string | null;
  filled_at: string | null;
}

export interface Position {
  symbol: string;
  qty: string;
  avg_entry: string;
  current_price: string;
  unrealized_pnl: string;
  realized_pnl: string;
}

export interface PlaceOrderRequest {
  symbol: string;
  side: OrderSide;
  qty: string;
  order_type: OrderType;
  limit_price?: string;
  market_price?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  order?: T;
  orders?: T[];
  positions?: T[];
  message?: string;
  close_order?: Order;
}

export interface ApiError {
  error: string;
  message: string;
}

/**
 * Place a new paper order.
 */
export async function placeOrder(request: PlaceOrderRequest): Promise<Order> {
  const res = await fetch(`${API_BASE}/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  const data = await res.json();

  if (!res.ok) {
    const err = data.detail as ApiError;
    throw new Error(err?.message || 'Failed to place order');
  }

  return data.order as Order;
}

/**
 * List orders with optional filters.
 */
export async function listOrders(params?: {
  symbol?: string;
  status?: OrderStatus;
}): Promise<Order[]> {
  const searchParams = new URLSearchParams();
  if (params?.symbol) searchParams.set('symbol', params.symbol);
  if (params?.status) searchParams.set('status', params.status);

  const url = `${API_BASE}/orders${searchParams.toString() ? `?${searchParams}` : ''}`;
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Failed to fetch orders');
  }

  const data = await res.json();
  return data.orders as Order[];
}

/**
 * Cancel a pending order.
 */
export async function cancelOrder(orderId: number): Promise<Order> {
  const res = await fetch(`${API_BASE}/orders/${orderId}`, {
    method: 'DELETE',
  });

  const data = await res.json();

  if (!res.ok) {
    const err = data.detail as ApiError;
    throw new Error(err?.message || 'Failed to cancel order');
  }

  return data.order as Order;
}

/**
 * List positions with optional symbol filter.
 */
export async function listPositions(symbol?: string): Promise<Position[]> {
  const url = symbol
    ? `${API_BASE}/positions?symbol=${encodeURIComponent(symbol)}`
    : `${API_BASE}/positions`;

  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Failed to fetch positions');
  }

  const data = await res.json();
  return data.positions as Position[];
}

/**
 * Close a position at market price.
 */
export async function closePosition(
  symbol: string,
  marketPrice: string
): Promise<Order> {
  const res = await fetch(
    `${API_BASE}/positions/${encodeURIComponent(symbol)}/close?market_price=${marketPrice}`,
    { method: 'POST' }
  );

  const data = await res.json();

  if (!res.ok) {
    const err = data.detail as ApiError;
    throw new Error(err?.message || 'Failed to close position');
  }

  return data.close_order as Order;
}
