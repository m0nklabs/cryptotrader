/**
 * Form for creating and editing alerts.
 */

import { useState } from 'react'
import type { AlertType, ComparisonOperator, CreateAlertRequest } from '../api/alerts'

type AlertFormProps = {
  onSubmit: (request: CreateAlertRequest) => void
  onCancel: () => void
  initialSymbol?: string
  initialExchange?: string
}

const ALERT_TYPES: { value: AlertType; label: string; description: string }[] = [
  { value: 'price_above', label: 'Price Above', description: 'Alert when price goes above threshold' },
  { value: 'price_below', label: 'Price Below', description: 'Alert when price goes below threshold' },
  {
    value: 'rsi_overbought',
    label: 'RSI Overbought',
    description: 'Alert when RSI goes above threshold (default 70)',
  },
  {
    value: 'rsi_oversold',
    label: 'RSI Oversold',
    description: 'Alert when RSI goes below threshold (default 30)',
  },
  { value: 'macd_cross_up', label: 'MACD Bullish Cross', description: 'Alert on MACD bullish crossover' },
  { value: 'macd_cross_down', label: 'MACD Bearish Cross', description: 'Alert on MACD bearish crossover' },
]

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']
const EXCHANGES = ['bitfinex', 'binance', 'kraken', 'coinbase']

export default function AlertForm({
  onSubmit,
  onCancel,
  initialSymbol = '',
  initialExchange = 'bitfinex',
}: AlertFormProps) {
  const [symbol, setSymbol] = useState(initialSymbol)
  const [exchange, setExchange] = useState(initialExchange)
  const [timeframe, setTimeframe] = useState('1h')
  const [alertType, setAlertType] = useState<AlertType>('price_above')
  const [operator, setOperator] = useState<ComparisonOperator>('crosses_above')
  const [value, setValue] = useState('')
  const [rsiPeriod, setRsiPeriod] = useState(14)
  const [enabled, setEnabled] = useState(true)

  const selectedAlertType = ALERT_TYPES.find(t => t.value === alertType)
  const isRsiAlert = alertType === 'rsi_overbought' || alertType === 'rsi_oversold'
  const isMacdAlert = alertType === 'macd_cross_up' || alertType === 'macd_cross_down'

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!symbol || !value) {
      alert('Please fill in all required fields')
      return
    }

    const request: CreateAlertRequest = {
      symbol: symbol.toUpperCase(),
      exchange,
      timeframe,
      condition: {
        type: alertType,
        operator: isMacdAlert ? 'crosses_above' : operator, // MACD always uses crossover
        value: parseFloat(value),
        indicator_params: isRsiAlert ? { period: rsiPeriod } : undefined,
      },
      enabled,
    }

    onSubmit(request)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            placeholder="BTCUSD"
            className="w-full px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
            required
          />
        </div>

        <div>
          <label className="block text-xs text-zinc-400 mb-1">Exchange</label>
          <select
            value={exchange}
            onChange={e => setExchange(e.target.value)}
            className="w-full px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
          >
            {EXCHANGES.map(ex => (
              <option key={ex} value={ex}>
                {ex}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-1">Timeframe</label>
        <select
          value={timeframe}
          onChange={e => setTimeframe(e.target.value)}
          className="w-full px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
        >
          {TIMEFRAMES.map(tf => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-1">Alert Type</label>
        <select
          value={alertType}
          onChange={e => setAlertType(e.target.value as AlertType)}
          className="w-full px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
        >
          {ALERT_TYPES.map(type => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
        {selectedAlertType && (
          <p className="text-xs text-zinc-500 mt-1">{selectedAlertType.description}</p>
        )}
      </div>

      {!isMacdAlert && (
        <div>
          <label className="block text-xs text-zinc-400 mb-1">Operator</label>
          <select
            value={operator}
            onChange={e => setOperator(e.target.value as ComparisonOperator)}
            className="w-full px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
          >
            <option value="above">Above</option>
            <option value="below">Below</option>
            <option value="crosses_above">Crosses Above</option>
            <option value="crosses_below">Crosses Below</option>
          </select>
        </div>
      )}

      <div>
        <label className="block text-xs text-zinc-400 mb-1">
          {isRsiAlert ? 'RSI Threshold' : isMacdAlert ? 'MACD Threshold' : 'Price Threshold'}
        </label>
        <input
          type="number"
          step="any"
          value={value}
          onChange={e => setValue(e.target.value)}
          placeholder={isRsiAlert ? '70' : isMacdAlert ? '0' : '50000'}
          className="w-full px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
          required
        />
      </div>

      {isRsiAlert && (
        <div>
          <label className="block text-xs text-zinc-400 mb-1">RSI Period</label>
          <input
            type="number"
            value={rsiPeriod}
            onChange={e => setRsiPeriod(parseInt(e.target.value) || 14)}
            className="w-full px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-white"
          />
        </div>
      )}

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="enabled"
          checked={enabled}
          onChange={e => setEnabled(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="enabled" className="text-sm text-zinc-300">
          Enable alert immediately
        </label>
      </div>

      <div className="flex gap-2 pt-2">
        <button
          type="submit"
          className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded text-sm font-medium"
        >
          Create Alert
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white rounded text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
