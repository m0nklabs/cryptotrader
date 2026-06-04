import { useState } from 'react';
import type { OrderSide, OrderType, PlaceOrderRequest } from '../api/trading';

interface OrderFormProps {
  symbol: string;
  currentPrice?: number;
  onSubmit: (request: PlaceOrderRequest) => Promise<void>;
  disabled?: boolean;
}

export default function OrderForm({
  symbol,
  currentPrice,
  onSubmit,
  disabled = false,
}: OrderFormProps) {
  const [side, setSide] = useState<OrderSide>('BUY');
  const [orderType, setOrderType] = useState<OrderType>('market');
  const [qty, setQty] = useState<string>('0.01');
  const [limitPrice, setLimitPrice] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    const qtyNum = parseFloat(qty);
    if (isNaN(qtyNum) || qtyNum <= 0) {
      setError('Quantity must be > 0');
      return;
    }

    if (orderType === 'limit') {
      const priceNum = parseFloat(limitPrice);
      if (isNaN(priceNum) || priceNum <= 0) {
        setError('Limit price must be > 0');
        return;
      }
    }

    if (orderType === 'market' && !currentPrice) {
      setError('Market price unavailable');
      return;
    }

    setLoading(true);
    try {
      const request: PlaceOrderRequest = {
        symbol,
        side,
        qty,
        order_type: orderType,
      };

      if (orderType === 'limit') {
        request.limit_price = limitPrice;
      } else {
        request.market_price = currentPrice?.toString();
      }

      await onSubmit(request);
      // Reset form on success
      setQty('0.01');
      setLimitPrice('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Order failed');
    } finally {
      setLoading(false);
    }
  };

  const quickFill = (pct: number) => {
    // Placeholder: in real use, would calculate from balance
    const base = 1;
    setQty((base * pct).toFixed(4));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      {/* Side toggle */}
      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => setSide('BUY')}
          disabled={disabled || loading}
          className={`flex-1 rounded px-2 py-1 text-xs font-medium transition ${
            side === 'BUY'
              ? 'bg-green-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
          }`}
        >
          BUY
        </button>
        <button
          type="button"
          onClick={() => setSide('SELL')}
          disabled={disabled || loading}
          className={`flex-1 rounded px-2 py-1 text-xs font-medium transition ${
            side === 'SELL'
              ? 'bg-red-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
          }`}
        >
          SELL
        </button>
      </div>

      {/* Order type */}
      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => setOrderType('market')}
          disabled={disabled || loading}
          className={`flex-1 rounded px-2 py-1 text-[10px] font-medium transition ${
            orderType === 'market'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300'
          }`}
        >
          MARKET
        </button>
        <button
          type="button"
          onClick={() => setOrderType('limit')}
          disabled={disabled || loading}
          className={`flex-1 rounded px-2 py-1 text-[10px] font-medium transition ${
            orderType === 'limit'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300'
          }`}
        >
          LIMIT
        </button>
      </div>

      {/* Quantity */}
      <div>
        <label className="block text-[10px] text-gray-600 dark:text-gray-400">
          Quantity
        </label>
        <input
          type="text"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          disabled={disabled || loading}
          className="mt-0.5 w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800"
          placeholder="0.01"
        />
        <div className="mt-1 flex gap-1">
          {[0.25, 0.5, 1].map((pct) => (
            <button
              key={pct}
              type="button"
              onClick={() => quickFill(pct)}
              disabled={disabled || loading}
              className="flex-1 rounded bg-gray-200 px-1 py-0.5 text-[9px] text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300"
            >
              {pct * 100}%
            </button>
          ))}
        </div>
      </div>

      {/* Limit price (conditional) */}
      {orderType === 'limit' && (
        <div>
          <label className="block text-[10px] text-gray-600 dark:text-gray-400">
            Limit Price
          </label>
          <input
            type="text"
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            disabled={disabled || loading}
            className="mt-0.5 w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800"
            placeholder={currentPrice?.toFixed(2) || '0.00'}
          />
        </div>
      )}

      {/* Market price display */}
      {orderType === 'market' && currentPrice !== undefined && (
        <div className="text-[10px] text-gray-500 dark:text-gray-400">
          Market: {currentPrice.toFixed(2)}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="rounded bg-red-100 px-2 py-1 text-[10px] text-red-700 dark:bg-red-900/30 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={disabled || loading}
        className={`w-full rounded px-2 py-1.5 text-xs font-medium text-white transition ${
          side === 'BUY'
            ? 'bg-green-600 hover:bg-green-700 disabled:bg-green-400'
            : 'bg-red-600 hover:bg-red-700 disabled:bg-red-400'
        }`}
      >
        {loading ? 'Placing...' : `${side} ${symbol}`}
      </button>
    </form>
  );
}
