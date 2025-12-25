import type { Order } from '../api/trading';

interface OrdersTableProps {
  orders: Order[];
  onCancel: (orderId: number) => Promise<void>;
  loading?: boolean;
}

export default function OrdersTable({
  orders,
  onCancel,
  loading = false,
}: OrdersTableProps) {
  if (orders.length === 0) {
    return (
      <div className="text-[10px] text-gray-500 dark:text-gray-400">
        No open orders
      </div>
    );
  }

  const formatTime = (ts: string | null) => {
    if (!ts) return '—';
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-600 dark:border-gray-700 dark:text-gray-400">
            <th className="pb-1 pr-2">Symbol</th>
            <th className="pb-1 pr-2">Side</th>
            <th className="pb-1 pr-2">Type</th>
            <th className="pb-1 pr-2 text-right">Qty</th>
            <th className="pb-1 pr-2 text-right">Price</th>
            <th className="pb-1 pr-2">Status</th>
            <th className="pb-1 pr-2">Time</th>
            <th className="pb-1"></th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr
              key={order.order_id}
              className="border-b border-gray-100 dark:border-gray-800"
            >
              <td className="py-1 pr-2 font-medium">{order.symbol}</td>
              <td className="py-1 pr-2">
                <span
                  className={
                    order.side === 'BUY'
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }
                >
                  {order.side}
                </span>
              </td>
              <td className="py-1 pr-2 text-gray-600 dark:text-gray-400">
                {order.order_type}
              </td>
              <td className="py-1 pr-2 text-right font-mono">
                {parseFloat(order.qty).toFixed(4)}
              </td>
              <td className="py-1 pr-2 text-right font-mono">
                {order.order_type === 'limit' && order.limit_price
                  ? parseFloat(order.limit_price).toFixed(2)
                  : order.fill_price
                    ? parseFloat(order.fill_price).toFixed(2)
                    : '—'}
              </td>
              <td className="py-1 pr-2">
                <span
                  className={`inline-block rounded px-1 py-0.5 text-[9px] font-medium ${
                    order.status === 'FILLED'
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : order.status === 'PENDING'
                        ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                        : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                  }`}
                >
                  {order.status}
                </span>
              </td>
              <td className="py-1 pr-2 text-gray-500 dark:text-gray-400">
                {formatTime(order.created_at)}
              </td>
              <td className="py-1">
                {order.status === 'PENDING' && (
                  <button
                    onClick={() => onCancel(order.order_id)}
                    disabled={loading}
                    className="rounded bg-red-100 px-1.5 py-0.5 text-[9px] text-red-700 hover:bg-red-200 disabled:opacity-50 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50"
                  >
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
