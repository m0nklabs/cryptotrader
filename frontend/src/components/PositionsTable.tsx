import type { Position } from '../api/trading';

interface PositionsTableProps {
  positions: Position[];
  onClose: (symbol: string) => Promise<void>;
  loading?: boolean;
}

export default function PositionsTable({
  positions,
  onClose,
  loading = false,
}: PositionsTableProps) {
  // Filter out zero-quantity positions
  const openPositions = positions.filter(
    (p) => parseFloat(p.qty) !== 0
  );

  if (openPositions.length === 0) {
    return (
      <div className="text-[10px] text-gray-500 dark:text-gray-400">
        No open positions
      </div>
    );
  }

  const formatPnl = (pnl: string) => {
    const num = parseFloat(pnl);
    const formatted = num.toFixed(2);
    return num >= 0 ? `+${formatted}` : formatted;
  };

  const pnlColor = (pnl: string) => {
    const num = parseFloat(pnl);
    if (num > 0) return 'text-green-600 dark:text-green-400';
    if (num < 0) return 'text-red-600 dark:text-red-400';
    return 'text-gray-600 dark:text-gray-400';
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-600 dark:border-gray-700 dark:text-gray-400">
            <th className="pb-1 pr-2">Symbol</th>
            <th className="pb-1 pr-2">Side</th>
            <th className="pb-1 pr-2 text-right">Qty</th>
            <th className="pb-1 pr-2 text-right">Entry</th>
            <th className="pb-1 pr-2 text-right">Current</th>
            <th className="pb-1 pr-2 text-right">Unreal. P&L</th>
            <th className="pb-1"></th>
          </tr>
        </thead>
        <tbody>
          {openPositions.map((pos) => {
            const qty = parseFloat(pos.qty);
            const side = qty > 0 ? 'LONG' : 'SHORT';

            return (
              <tr
                key={pos.symbol}
                className="border-b border-gray-100 dark:border-gray-800"
              >
                <td className="py-1 pr-2 font-medium">{pos.symbol}</td>
                <td className="py-1 pr-2">
                  <span
                    className={
                      side === 'LONG'
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-red-600 dark:text-red-400'
                    }
                  >
                    {side}
                  </span>
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {Math.abs(qty).toFixed(4)}
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {parseFloat(pos.avg_entry).toFixed(2)}
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {parseFloat(pos.current_price).toFixed(2)}
                </td>
                <td
                  className={`py-1 pr-2 text-right font-mono font-medium ${pnlColor(
                    pos.unrealized_pnl
                  )}`}
                >
                  {formatPnl(pos.unrealized_pnl)}
                </td>
                <td className="py-1">
                  <button
                    onClick={() => onClose(pos.symbol)}
                    disabled={loading}
                    className="rounded bg-gray-200 px-1.5 py-0.5 text-[9px] text-gray-700 hover:bg-gray-300 disabled:opacity-50 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                  >
                    Close
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
