/**
 * React Query hooks for portfolio data fetching.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getPortfolioSnapshots,
  getLatestPortfolioSnapshot,
  getPositionHistory,
  getBalanceHistory,
  PortfolioSnapshot,
  PositionHistory,
  BalanceSnapshot,
} from '../api/portfolio';

/**
 * Hook to fetch portfolio snapshots for equity curve.
 */
export function usePortfolioSnapshots(params?: {
  start_time?: string;
  end_time?: string;
  limit?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ['portfolio', 'snapshots', params?.start_time, params?.end_time, params?.limit],
    queryFn: () => getPortfolioSnapshots(params),
    enabled: params?.enabled ?? true,
    refetchInterval: 30000, // Refetch every 30 seconds
    retry: 2,
  });
}

/**
 * Hook to fetch the latest portfolio snapshot.
 */
export function useLatestPortfolioSnapshot(enabled: boolean = true) {
  return useQuery({
    queryKey: ['portfolio', 'latest'],
    queryFn: getLatestPortfolioSnapshot,
    enabled,
    refetchInterval: 10000, // Refetch every 10 seconds
    retry: 2,
  });
}

/**
 * Hook to fetch position history.
 */
export function usePositionHistory(params?: {
  symbol?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ['portfolio', 'positions', 'history', params?.symbol, params?.start_time, params?.end_time, params?.limit],
    queryFn: () => getPositionHistory(params),
    enabled: params?.enabled ?? true,
    refetchInterval: 30000,
    retry: 2,
  });
}

/**
 * Hook to fetch balance history.
 */
export function useBalanceHistory(params?: {
  exchange?: string;
  currency?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ['portfolio', 'balances', 'history', params?.exchange, params?.currency, params?.start_time, params?.end_time, params?.limit],
    queryFn: () => getBalanceHistory(params),
    enabled: params?.enabled ?? true,
    refetchInterval: 30000,
    retry: 2,
  });
}
