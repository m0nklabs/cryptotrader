/**
 * Watchlist API client.
 * Connects to backend endpoints for watchlist management.
 */

const API_BASE = '/api';

export interface Watchlist {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  id: number;
  exchange: string;
  symbol: string;
  sort_order: number;
  notes: string | null;
}

export interface ColumnPreference {
  id: number;
  column_name: string;
  is_visible: boolean;
  sort_order: number;
  width: number | null;
}

export interface WatchlistDetail {
  watchlist: Watchlist;
  items: WatchlistItem[];
  columns: ColumnPreference[];
}

/**
 * List all watchlists.
 */
export async function listWatchlists(): Promise<Watchlist[]> {
  const res = await fetch(`${API_BASE}/watchlist/`);

  if (!res.ok) {
    throw new Error('Failed to fetch watchlists');
  }

  const data = await res.json();
  return data.watchlists as Watchlist[];
}

/**
 * Get a specific watchlist with items and column preferences.
 */
export async function getWatchlist(watchlistId: number): Promise<WatchlistDetail> {
  const res = await fetch(`${API_BASE}/watchlist/${watchlistId}`);

  if (!res.ok) {
    throw new Error('Failed to fetch watchlist');
  }

  return (await res.json()) as WatchlistDetail;
}

/**
 * Create a new watchlist.
 */
export async function createWatchlist(
  name: string,
  description?: string,
  is_default: boolean = false
): Promise<{ watchlist_id: number }> {
  const res = await fetch(`${API_BASE}/watchlist/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description, is_default }),
  });

  if (!res.ok) {
    throw new Error('Failed to create watchlist');
  }

  return await res.json();
}

/**
 * Update a watchlist.
 */
export async function updateWatchlist(
  watchlistId: number,
  updates: {
    name?: string;
    description?: string;
    is_default?: boolean;
  }
): Promise<void> {
  const res = await fetch(`${API_BASE}/watchlist/${watchlistId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });

  if (!res.ok) {
    throw new Error('Failed to update watchlist');
  }
}

/**
 * Delete a watchlist.
 */
export async function deleteWatchlist(watchlistId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/watchlist/${watchlistId}`, {
    method: 'DELETE',
  });

  if (!res.ok) {
    throw new Error('Failed to delete watchlist');
  }
}

/**
 * Add a symbol to a watchlist.
 */
export async function addWatchlistItem(
  watchlistId: number,
  exchange: string,
  symbol: string,
  notes?: string
): Promise<{ item_id: number }> {
  const res = await fetch(`${API_BASE}/watchlist/${watchlistId}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ exchange, symbol, notes }),
  });

  if (!res.ok) {
    throw new Error('Failed to add watchlist item');
  }

  return await res.json();
}

/**
 * Remove an item from a watchlist.
 */
export async function removeWatchlistItem(itemId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/watchlist/items/${itemId}`, {
    method: 'DELETE',
  });

  if (!res.ok) {
    throw new Error('Failed to remove watchlist item');
  }
}

/**
 * Update the sort order of a watchlist item.
 */
export async function updateWatchlistItemOrder(
  itemId: number,
  sortOrder: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/watchlist/items/${itemId}/order`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sort_order: sortOrder }),
  });

  if (!res.ok) {
    throw new Error('Failed to update item order');
  }
}

/**
 * Set column preference for a watchlist.
 */
export async function setColumnPreference(
  watchlistId: number,
  columnName: string,
  isVisible: boolean,
  sortOrder?: number,
  width?: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/watchlist/${watchlistId}/columns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      column_name: columnName,
      is_visible: isVisible,
      sort_order: sortOrder,
      width,
    }),
  });

  if (!res.ok) {
    throw new Error('Failed to set column preference');
  }
}
