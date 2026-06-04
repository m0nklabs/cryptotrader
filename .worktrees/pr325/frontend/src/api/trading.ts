/**
 * Paper trading API client.
 * Connects to backend endpoints for order and position management.
 */

const API_BASE = '/api';
// Wallets-data service for real exchange data (not yet deployed)
const WALLETS_API = 'http://localhost:8101';
// Flag to indicate wallets-data service is available
const WALLETS_SERVICE_ENABLED = false;

export type OrderSide = 'BUY' | 'SELL' | 'buy' | 'sell';
export type OrderType = 'market' | 'limit' | string;  // Bitfinex uses 'EXCHANGE LIMIT' etc.
export type OrderStatus = 'PENDING' | 'FILLED' | 'CANCELLED' | 'ACTIVE' | string;

export interface Order {
  order_id: number;
  symbol: string;
  side: OrderSide;
  order_type: OrderType;
  // Paper trading fields
  qty?: string;
  limit_price?: string | null;
  fill_price?: string | null;
  slippage_bps?: string | null;
  filled_at?: string | null;
  // Exchange order fields (from wallets-data)
  exchange?: string;
  amount?: string;
  amount_filled?: string;
  price?: string | null;
  avg_price?: string | null;
  status: OrderStatus;
  created_at: string | null;
  updated_at?: string | null;
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
 * List orders - fetches real orders from wallets-data service.
 * Returns empty array if service is not available.
 */
export async function listOrders(params?: {
  symbol?: string;
  status?: OrderStatus;
}): Promise<Order[]> {
  // Wallets-data service not yet deployed
  if (!WALLETS_SERVICE_ENABLED) {
    return [];
  }

  // Fetch real orders from wallets-data (Bitfinex)
  const res = await fetch(`${WALLETS_API}/orders`);

  if (!res.ok) {
    throw new Error('Failed to fetch orders');
  }

  const data = await res.json();
  let orders = data.orders as Order[];

  // Apply filters client-side
  if (params?.symbol) {
    orders = orders.filter(o => o.symbol === params.symbol);
  }
  if (params?.status) {
    orders = orders.filter(o => o.status === params.status);
  }

  return orders;
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
