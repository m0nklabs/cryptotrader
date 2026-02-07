import SpreadTable from './SpreadTable'
import { useArbitrage } from '../hooks/useArbitrage'

type ArbitragePanelProps = {
  exchanges: string[]
  timeframe: string
}

export default function ArbitragePanel({ exchanges, timeframe }: ArbitragePanelProps) {
  const { data, isLoading, error } = useArbitrage({
    exchanges,
    timeframe,
    minProfitPct: 0.5,
  })

  if (isLoading) {
    return <div className="text-xs text-gray-500">Loading arbitrage spreads...</div>
  }

  if (error) {
    return <div className="text-xs text-red-500">Unable to load arbitrage data.</div>
  }

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
        Cross-exchange spreads
      </div>
      <SpreadTable opportunities={data?.opportunities ?? []} />
    </div>
  )
}
