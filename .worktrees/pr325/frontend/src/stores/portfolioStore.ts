/**
 * Portfolio state store using Zustand.
 */

import { create } from 'zustand';
import { PortfolioSnapshot, PositionHistory } from '../api/portfolio';

interface PortfolioStore {
  // Current snapshot
  currentSnapshot: PortfolioSnapshot | null;
  setCurrentSnapshot: (snapshot: PortfolioSnapshot | null) => void;

  // Historical snapshots for equity curve
  snapshots: PortfolioSnapshot[];
  setSnapshots: (snapshots: PortfolioSnapshot[]) => void;

  // Position history
  positionHistory: PositionHistory[];
  setPositionHistory: (history: PositionHistory[]) => void;

  // Selected symbol for filtering
  selectedSymbol: string | null;
  setSelectedSymbol: (symbol: string | null) => void;

  // Time range for charts
  timeRange: '1D' | '1W' | '1M' | '3M' | '1Y' | 'ALL';
  setTimeRange: (range: '1D' | '1W' | '1M' | '3M' | '1Y' | 'ALL') => void;
}

export const usePortfolioStore = create<PortfolioStore>((set) => ({
  currentSnapshot: null,
  setCurrentSnapshot: (snapshot) => set({ currentSnapshot: snapshot }),

  snapshots: [],
  setSnapshots: (snapshots) => set({ snapshots }),

  positionHistory: [],
  setPositionHistory: (history) => set({ positionHistory: history }),

  selectedSymbol: null,
  setSelectedSymbol: (symbol) => set({ selectedSymbol: symbol }),

  timeRange: '1W',
  setTimeRange: (range) => set({ timeRange: range }),
}));
