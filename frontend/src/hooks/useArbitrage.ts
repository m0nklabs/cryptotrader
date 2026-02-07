import { useQuery } from '@tanstack/react-query'

// All API calls use relative paths, proxied by Vite to the backend

export type ArbitrageOpportunity = {
  symbol: string
  buy_exchange: string
  sell_exchange: string
  buy_price: number
  sell_price: number
  spread_pct: number
  net_profit: number
  net_profit_pct: number
  total_fees: number
}

type UseArbitrageOptions = {
  exchanges: string[]
  timeframe: string
  minProfitPct?: number
  symbols?: string[]
  enabled?: boolean
}

export function useArbitrage({
  exchanges,
  timeframe,
  minProfitPct = 0.5,
  symbols,
  enabled = true,
}: UseArbitrageOptions) {
  return useQuery({
    queryKey: ['arbitrage', exchanges.join(','), timeframe, minProfitPct, symbols?.join(',') ?? ''],
    queryFn: async () => {
      const params = new URLSearchParams({
        exchanges: exchanges.join(','),
        timeframe,
        min_profit_pct: minProfitPct.toString(),
      })
      if (symbols && symbols.length) {
        params.set('symbols', symbols.join(','))
      }

      const response = await fetch(`/arbitrage/opportunities?${params.toString()}`)
      if (!response.ok) {
        throw new Error('Failed to fetch arbitrage opportunities')
      }
      return response.json() as Promise<{ opportunities: ArbitrageOpportunity[] }>
    },
    enabled,
    refetchInterval: 10000,
    retry: 2,
  })
}
