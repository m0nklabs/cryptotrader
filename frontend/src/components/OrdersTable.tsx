import type { Order, OrderStatus } from '../api/trading';

interface OrdersTableProps {
  orders: Order[];
  onCancel: (orderId: number) => Promise<void>;
  loading?: boolean;
}

// Every executor state gets its own colour so a PARTIAL or MISSED fill never
// disappears into the neutral default.
const STATUS_CLASSES: Record<OrderStatus, string> = {
  FILLED: 'text-[var(--success)]',
  PARTIAL: 'text-[var(--info)]',
  PENDING: 'text-[var(--warn)]',
  MISSED: 'text-[var(--danger)]',
  CANCELLED: 'text-[var(--muted)]',
};

const BADGE_CLASSES =
  'inline-block rounded border border-[var(--line)] bg-[var(--panel-2)] px-1 py-0.5 text-[9px] font-medium';

function parseNumber(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function OrdersTable({
  orders,
  onCancel,
  loading = false,
}: OrdersTableProps) {
  if (orders.length === 0) {
    return (
      <div className="text-[10px] text-[var(--muted)]">No orders</div>
    );
  }

  const formatTime = (ts: string | null) => {
    if (!ts) return '—';
    return new Date(ts).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatQty = (value: string | null): string => {
    const parsed = parseNumber(value);
    return parsed === null ? '—' : parsed.toFixed(4);
  };

  const formatPercent = (value: string | null): string => {
    const parsed = parseNumber(value);
    return parsed === null ? '—' : `${(parsed * 100).toFixed(0)}%`;
  };

  const formatPrice = (value: string | null): string => {
    const parsed = parseNumber(value);
    return parsed === null ? '—' : parsed.toFixed(2);
  };

  const canCancel = (order: Order): boolean => order.status === 'PENDING';

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="border-b border-[var(--line)] text-left text-[var(--muted)]">
            <th className="pb-1 pr-2">Symbol</th>
            <th className="pb-1 pr-2">Side</th>
            <th className="pb-1 pr-2">Type</th>
            <th className="pb-1 pr-2">Mode</th>
            <th className="pb-1 pr-2 text-right">Qty</th>
            <th className="pb-1 pr-2 text-right">Filled</th>
            <th className="pb-1 pr-2 text-right">Rem.</th>
            <th className="pb-1 pr-2 text-right">Avg fill</th>
            <th className="pb-1 pr-2 text-right">Fees</th>
            <th className="pb-1 pr-2 text-right">Slip</th>
            <th className="pb-1 pr-2">Status</th>
            <th className="pb-1 pr-2">Time</th>
            <th className="pb-1"></th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => {
            const isBuy = order.side === 'BUY';

            return (
              <tr
                key={order.order_id}
                className="border-b border-[var(--line)]"
              >
                <td className="py-1 pr-2 font-medium">{order.symbol}</td>
                <td className="py-1 pr-2">
                  <span
                    className={
                      isBuy ? 'text-[var(--success)]' : 'text-[var(--danger)]'
                    }
                  >
                    {order.side}
                  </span>
                </td>
                <td className="py-1 pr-2 text-[var(--muted)]">
                  {order.order_type}
                </td>
                <td className="py-1 pr-2">
                  <span
                    className={`${BADGE_CLASSES} uppercase tracking-wide text-[var(--violet)]`}
                    title="Order source: orders served by the paper executor"
                  >
                    {order.mode}
                  </span>
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {formatQty(order.requested_qty)}
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {formatQty(order.filled_qty)}
                  <span className="ml-1 text-[var(--muted)]">
                    {formatPercent(order.fill_ratio)}
                  </span>
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {formatQty(order.remaining_qty)}
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  <div>{formatPrice(order.avg_fill_price)}</div>
                  {/* A resting limit order has no fill price yet, so the
                      execution threshold must stay visible on its own line. */}
                  {order.limit_price !== null && (
                    <div
                      className="text-[9px] text-[var(--muted)]"
                      title="Resting limit price"
                    >
                      limit {formatPrice(order.limit_price)}
                    </div>
                  )}
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {formatPrice(order.fees)}
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  {order.slippage_bps ? `${order.slippage_bps} bps` : '—'}
                </td>
                <td className="py-1 pr-2">
                  <span className={`${BADGE_CLASSES} ${STATUS_CLASSES[order.status]}`}>
                    {order.status}
                  </span>
                </td>
                <td
                  className="py-1 pr-2 text-[var(--muted)]"
                  title={order.filled_at ? `Filled ${order.filled_at}` : undefined}
                >
                  {formatTime(order.created_at)}
                </td>
                <td className="py-1">
                  {canCancel(order) && (
                    <button
                      onClick={() => onCancel(order.order_id)}
                      disabled={loading}
                      className="rounded border border-[var(--line)] bg-[var(--panel-2)] px-1.5 py-0.5 text-[9px] text-[var(--danger)] hover:border-[var(--danger)] disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
