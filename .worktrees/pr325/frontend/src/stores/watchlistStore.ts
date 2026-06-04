/**
 * Watchlist state store using Zustand.
 */

import { create } from 'zustand';
import { Watchlist, WatchlistDetail } from '../api/watchlist';

interface WatchlistStore {
  // All watchlists
  watchlists: Watchlist[];
  setWatchlists: (watchlists: Watchlist[]) => void;

  // Currently selected watchlist
  selectedWatchlistId: number | null;
  setSelectedWatchlistId: (id: number | null) => void;

  // Currently selected watchlist detail (with items and columns)
  selectedWatchlist: WatchlistDetail | null;
  setSelectedWatchlist: (detail: WatchlistDetail | null) => void;

  // Column selector visibility
  showColumnSelector: boolean;
  setShowColumnSelector: (show: boolean) => void;

  // Symbol search visibility
  showSymbolSearch: boolean;
  setShowSymbolSearch: (show: boolean) => void;
}

export const useWatchlistStore = create<WatchlistStore>((set) => ({
  watchlists: [],
  setWatchlists: (watchlists) => set({ watchlists }),

  selectedWatchlistId: null,
  setSelectedWatchlistId: (id) => set({ selectedWatchlistId: id }),

  selectedWatchlist: null,
  setSelectedWatchlist: (detail) => set({ selectedWatchlist: detail }),

  showColumnSelector: false,
  setShowColumnSelector: (show) => set({ showColumnSelector: show }),

  showSymbolSearch: false,
  setShowSymbolSearch: (show) => set({ showSymbolSearch: show }),
}));
