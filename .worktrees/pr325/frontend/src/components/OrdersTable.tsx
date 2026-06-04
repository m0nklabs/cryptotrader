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

  const formatTime = (ts: string | null | undefined) => {
    if (!ts) return '—';
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Helper to get quantity - works for both paper trading (qty) and exchange orders (amount)
  const getQty = (order: Order): string => {
    const qty = order.qty || order.amount || '0';
    return parseFloat(qty).toFixed(4);
  };

  // Helper to get price - works for both paper trading and exchange orders
  const getPrice = (order: Order): string => {
    const price = order.limit_price || order.price || order.fill_price || order.avg_price;
    if (!price) return '—';
    return parseFloat(price).toFixed(2);
  };

  // Helper to normalize side display
  const getSide = (order: Order): string => {
    return order.side.toUpperCase();
  };

  // Helper to check if side is buy
  const isBuy = (order: Order): boolean => {
    return order.side.toUpperCase() === 'BUY';
  };

  // Helper to check if order can be cancelled
  const canCancel = (order: Order): boolean => {
    const status = order.status.toUpperCase();
    return status === 'PENDING' || status === 'ACTIVE';
  };

  // Helper to get status color classes
  const getStatusClasses = (order: Order): string => {
    const status = order.status.toUpperCase();
    if (status === 'FILLED' || status === 'EXECUTED') {
      return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
    }
    if (status === 'PENDING' || status === 'ACTIVE') {
      return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
    }
    return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400';
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
                    isBuy(order)
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }
                >
                  {getSide(order)}
                </span>
              </td>
              <td className="py-1 pr-2 text-gray-600 dark:text-gray-400">
                {order.order_type}
              </td>
              <td className="py-1 pr-2 text-right font-mono">
                {getQty(order)}
              </td>
              <td className="py-1 pr-2 text-right font-mono">
                {getPrice(order)}
              </td>
              <td className="py-1 pr-2">
                <span
                  className={`inline-block rounded px-1 py-0.5 text-[9px] font-medium ${getStatusClasses(order)}`}
                >
                  {order.status}
                </span>
              </td>
              <td className="py-1 pr-2 text-gray-500 dark:text-gray-400">
                {formatTime(order.created_at)}
              </td>
              <td className="py-1">
                {canCancel(order) && (
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
