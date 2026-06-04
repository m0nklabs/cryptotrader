/**
 * Portfolio API client.
 * Connects to backend endpoints for portfolio tracking and P&L.
 */

const API_BASE = '/api';

export interface PortfolioSnapshot {
  id: number;
  timestamp: string;
  total_equity: string;
  cash_balance: string;
  position_value: string;
  unrealized_pnl: string;
  realized_pnl: string;
  total_pnl: string;
  quote_currency: string;
}

export interface PositionHistory {
  id: number;
  timestamp: string;
  symbol: string;
  exchange: string;
  quantity: string;
  avg_entry_price: string;
  current_price: string;
  unrealized_pnl: string;
  realized_pnl: string;
  cost_basis: string;
}

export interface BalanceSnapshot {
  id: number;
  timestamp: string;
  exchange: string;
  currency: string;
  available: string;
  reserved: string;
  total: string;
}

/**
 * Get portfolio snapshots for equity curve.
 */
export async function getPortfolioSnapshots(params?: {
  start_time?: string;
  end_time?: string;
  limit?: number;
}): Promise<PortfolioSnapshot[]> {
  const queryParams = new URLSearchParams();
  if (params?.start_time) queryParams.set('start_time', params.start_time);
  if (params?.end_time) queryParams.set('end_time', params.end_time);
  if (params?.limit) queryParams.set('limit', params.limit.toString());

  const url = `${API_BASE}/portfolio/snapshots?${queryParams}`;
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Failed to fetch portfolio snapshots');
  }

  const data = await res.json();
  return data.snapshots as PortfolioSnapshot[];
}

/**
 * Get the latest portfolio snapshot.
 */
export async function getLatestPortfolioSnapshot(): Promise<PortfolioSnapshot> {
  const res = await fetch(`${API_BASE}/portfolio/snapshots/latest`);

  if (!res.ok) {
    throw new Error('Failed to fetch latest portfolio snapshot');
  }

  const data = await res.json();
  return data.snapshot as PortfolioSnapshot;
}

/**
 * Get position history for a symbol.
 */
export async function getPositionHistory(params?: {
  symbol?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}): Promise<PositionHistory[]> {
  const queryParams = new URLSearchParams();
  if (params?.symbol) queryParams.set('symbol', params.symbol);
  if (params?.start_time) queryParams.set('start_time', params.start_time);
  if (params?.end_time) queryParams.set('end_time', params.end_time);
  if (params?.limit) queryParams.set('limit', params.limit.toString());

  const url = `${API_BASE}/portfolio/positions/history?${queryParams}`;
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Failed to fetch position history');
  }

  const data = await res.json();
  return data.history as PositionHistory[];
}

/**
 * Get balance history.
 */
export async function getBalanceHistory(params?: {
  exchange?: string;
  currency?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}): Promise<BalanceSnapshot[]> {
  const queryParams = new URLSearchParams();
  if (params?.exchange) queryParams.set('exchange', params.exchange);
  if (params?.currency) queryParams.set('currency', params.currency);
  if (params?.start_time) queryParams.set('start_time', params.start_time);
  if (params?.end_time) queryParams.set('end_time', params.end_time);
  if (params?.limit) queryParams.set('limit', params.limit.toString());

  const url = `${API_BASE}/portfolio/balances/history?${queryParams}`;
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error('Failed to fetch balance history');
  }

  const data = await res.json();
  return data.history as BalanceSnapshot[];
}
