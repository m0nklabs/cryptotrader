/**
 * Market cap rankings API client.
 * Fetches live market cap data from CoinGecko via backend API.
 */

const API_BASE = '/api';

export interface MarketCapResponse {
  rankings: Record<string, number>;
  cached: boolean;
  source: 'coingecko' | 'fallback';
  last_updated: number | null;
}

/**
 * Fetch current market cap rankings from backend.
 */
export async function fetchMarketCap(signal?: AbortSignal): Promise<MarketCapResponse> {
  const res = await fetch(`${API_BASE}/market-cap`, { signal });

  if (!res.ok) {
    throw new Error(`Failed to fetch market cap: ${res.status}`);
  }

  return res.json();
}
