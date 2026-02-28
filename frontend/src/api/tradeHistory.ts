/**
 * Trade history API client.
 * Connects to backend endpoints for trade execution history and order audit logs.
 */

const API_BASE = '/api';

export interface Trade {
  id: number;
  trade_id: string;
  order_id: string | null;
  exchange: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  fee: string;
  fee_currency: string | null;
  quote_qty: string;
  trade_type: string;
  execution_time: string;
  is_paper: boolean;
}

export interface OrderAuditLog {
  id: number;
  order_id: string;
  exchange: string;
  symbol: string;
  side: string;
  order_type: string;
  status: string;
  event_type: string;
  event_time: string;
  quantity: string | null;
  filled_quantity: string | null;
  limit_price: string | null;
  stop_price: string | null;
  avg_fill_price: string | null;
  metadata: Record<string, any> | null;
}

/**
 * List trade executions with optional filters.
 */
export async function listTrades(params?: {
  symbol?: string;
  start_time?: string;
  end_time?: string;
  is_paper?: boolean;
  limit?: number;
}): Promise<Trade[]> {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.set('symbol', params.symbol);
  if (params?.start_time) queryParams.set('start_time', params.start_time);
  if (params?.end_time) queryParams.set('end_time', params.end_time);
  if (params?.is_paper !== undefined) queryParams.set('is_paper', params.is_paper.toString());
  if (params?.limit) queryParams.set('limit', params.limit.toString());

  const url = `${API_BASE}/trades/?${queryParams}`;
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Failed to fetch trades');
  }

  const data = await res.json();
  return data.trades as Trade[];
}

/**
 * Get a specific trade by ID.
 */
export async function getTrade(tradeId: string): Promise<Trade> {
  const res = await fetch(`${API_BASE}/trades/${tradeId}`);

  if (!res.ok) {
    throw new Error('Failed to fetch trade');
  }

  const data = await res.json();
  return data.trade as Trade;
}

/**
 * Get order audit log with optional filters.
 */
export async function getOrderAuditLog(params?: {
  order_id?: string;
  symbol?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}): Promise<OrderAuditLog[]> {
  const queryParams = new URLSearchParams();
  if (params?.order_id) queryParams.set('order_id', params.order_id);
  if (params?.symbol) queryParams.set('symbol', params.symbol);
  if (params?.start_time) queryParams.set('start_time', params.start_time);
  if (params?.end_time) queryParams.set('end_time', params.end_time);
  if (params?.limit) queryParams.set('limit', params.limit.toString());

  const url = `${API_BASE}/trades/audit?${queryParams}`;
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Failed to fetch order audit log');
  }

  const data = await res.json();
  return data.audit_log as OrderAuditLog[];
}
