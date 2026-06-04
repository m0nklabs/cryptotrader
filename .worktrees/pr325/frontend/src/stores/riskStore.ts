/**
 * Risk calculator state store using Zustand.
 */

import { create } from 'zustand';

interface RiskStore {
  // Account settings
  accountSize: number;
  setAccountSize: (size: number) => void;

  riskPercentage: number;
  setRiskPercentage: (percentage: number) => void;

  // Trade parameters
  entryPrice: number;
  setEntryPrice: (price: number) => void;

  stopLossPrice: number;
  setStopLossPrice: (price: number) => void;

  takeProfitPrice: number | null;
  setTakeProfitPrice: (price: number | null) => void;

  // Trade direction
  isLong: boolean;
  setIsLong: (isLong: boolean) => void;

  // Leverage
  leverage: number;
  setLeverage: (leverage: number) => void;

  // Target risk/reward ratio
  targetRR: number;
  setTargetRR: (ratio: number) => void;

  // Reset to defaults
  reset: () => void;
}

const DEFAULT_VALUES = {
  accountSize: 10000,
  riskPercentage: 1,
  entryPrice: 0,
  stopLossPrice: 0,
  takeProfitPrice: null,
  isLong: true,
  leverage: 1,
  targetRR: 2,
};

export const useRiskStore = create<RiskStore>((set) => ({
  ...DEFAULT_VALUES,

  setAccountSize: (size) => set({ accountSize: size }),
  setRiskPercentage: (percentage) => set({ riskPercentage: percentage }),
  setEntryPrice: (price) => set({ entryPrice: price }),
  setStopLossPrice: (price) => set({ stopLossPrice: price }),
  setTakeProfitPrice: (price) => set({ takeProfitPrice: price }),
  setIsLong: (isLong) => set({ isLong }),
  setLeverage: (leverage) => set({ leverage }),
  setTargetRR: (ratio) => set({ targetRR: ratio }),

  reset: () => set(DEFAULT_VALUES),
}));
