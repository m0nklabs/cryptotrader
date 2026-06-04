import type { ArbitrageOpportunity } from '../hooks/useArbitrage'

type SpreadTableProps = {
  opportunities: ArbitrageOpportunity[]
}

export default function SpreadTable({ opportunities }: SpreadTableProps) {
  if (opportunities.length === 0) {
    return <div className="text-xs text-gray-500">No cross-exchange spreads above threshold.</div>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="py-1 text-left font-medium">Symbol</th>
            <th className="py-1 text-left font-medium">Buy</th>
            <th className="py-1 text-left font-medium">Sell</th>
            <th className="py-1 text-right font-medium">Spread %</th>
            <th className="py-1 text-right font-medium">Net %</th>
          </tr>
        </thead>
        <tbody>
          {opportunities.map((opp) => (
            <tr key={`${opp.symbol}-${opp.buy_exchange}-${opp.sell_exchange}`} className="border-b border-gray-100 dark:border-gray-800">
              <td className="py-1.5 font-medium">{opp.symbol}</td>
              <td className="py-1.5 text-left">
                {opp.buy_exchange} @ ${opp.buy_price.toFixed(2)}
              </td>
              <td className="py-1.5 text-left">
                {opp.sell_exchange} @ ${opp.sell_price.toFixed(2)}
              </td>
              <td className="py-1.5 text-right">{opp.spread_pct.toFixed(2)}%</td>
              <td className={`py-1.5 text-right ${opp.net_profit_pct >= 0.5 ? 'text-green-500' : 'text-gray-500'}`}>
                {opp.net_profit_pct.toFixed(2)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
