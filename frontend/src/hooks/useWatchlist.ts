/**
 * React Query hooks for watchlist data fetching.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listWatchlists,
  getWatchlist,
  createWatchlist,
  updateWatchlist,
  deleteWatchlist,
  addWatchlistItem,
  removeWatchlistItem,
  Watchlist,
  WatchlistDetail,
} from '../api/watchlist';

/**
 * Hook to fetch all watchlists.
 */
export function useWatchlists(enabled: boolean = true) {
  return useQuery({
    queryKey: ['watchlists'],
    queryFn: listWatchlists,
    enabled,
    refetchInterval: 60000, // Refetch every 60 seconds
    retry: 2,
  });
}

/**
 * Hook to fetch a specific watchlist with items and columns.
 */
export function useWatchlist(watchlistId: number | null, enabled: boolean = true) {
  return useQuery({
    queryKey: ['watchlist', watchlistId],
    queryFn: () => getWatchlist(watchlistId!),
    enabled: enabled && watchlistId !== null,
    refetchInterval: 30000,
    retry: 2,
  });
}

/**
 * Hook to create a new watchlist.
 */
export function useCreateWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ name, description, is_default }: {
      name: string;
      description?: string;
      is_default?: boolean;
    }) => createWatchlist(name, description, is_default),
    onSuccess: () => {
      // Invalidate watchlists query to refetch
      queryClient.invalidateQueries({ queryKey: ['watchlists'] });
    },
  });
}

/**
 * Hook to update a watchlist.
 */
export function useUpdateWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ watchlistId, updates }: {
      watchlistId: number;
      updates: { name?: string; description?: string; is_default?: boolean };
    }) => updateWatchlist(watchlistId, updates),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['watchlists'] });
      queryClient.invalidateQueries({ queryKey: ['watchlist', variables.watchlistId] });
    },
  });
}

/**
 * Hook to delete a watchlist.
 */
export function useDeleteWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (watchlistId: number) => deleteWatchlist(watchlistId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlists'] });
    },
  });
}

/**
 * Hook to add an item to a watchlist.
 */
export function useAddWatchlistItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ watchlistId, exchange, symbol, notes }: {
      watchlistId: number;
      exchange: string;
      symbol: string;
      notes?: string;
    }) => addWatchlistItem(watchlistId, exchange, symbol, notes),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['watchlist', variables.watchlistId] });
    },
  });
}

/**
 * Hook to remove an item from a watchlist.
 */
export function useRemoveWatchlistItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, watchlistId }: { itemId: number; watchlistId: number }) =>
      removeWatchlistItem(itemId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['watchlist', variables.watchlistId] });
    },
  });
}
