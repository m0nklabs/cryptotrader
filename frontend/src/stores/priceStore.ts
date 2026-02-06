import { create } from 'zustand'

export type PriceStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export type PriceSnapshot = {
  exchange: string
  symbol: string
  price: number
  timestamp: number
}

type PriceState = {
  prices: Record<string, PriceSnapshot>
  statusByExchange: Record<string, PriceStatus>
  setPrice: (snapshot: PriceSnapshot) => void
  setStatus: (exchange: string, status: PriceStatus) => void
}

const keyFor = (exchange: string, symbol: string) => `${exchange}:${symbol}`

export const usePriceStore = create<PriceState>((set) => ({
  prices: {},
  statusByExchange: {},
  setPrice: (snapshot) =>
    set((state) => ({
      prices: {
        ...state.prices,
        [keyFor(snapshot.exchange, snapshot.symbol)]: snapshot,
      },
    })),
  setStatus: (exchange, status) =>
    set((state) => ({
      statusByExchange: {
        ...state.statusByExchange,
        [exchange]: status,
      },
    })),
}))
