import { create } from 'zustand'

export type ExchangeOption = 'bitfinex' | 'binance'

type ExchangeState = {
  selectedExchange: ExchangeOption
  setExchange: (exchange: ExchangeOption) => void
}

const STORAGE_KEY = 'selected-exchange'

const loadExchange = (): ExchangeOption => {
  if (typeof window === 'undefined') return 'bitfinex'
  const saved = window.localStorage.getItem(STORAGE_KEY)
  if (saved === 'bitfinex' || saved === 'binance') return saved
  return 'bitfinex'
}

export const useExchangeStore = create<ExchangeState>((set) => ({
  selectedExchange: loadExchange(),
  setExchange: (exchange) => {
    set({ selectedExchange: exchange })
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, exchange)
    }
  },
}))
