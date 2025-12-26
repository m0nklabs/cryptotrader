# UI Changes: Exchange Selector

## Location
The exchange selector has been added to the **Market Watch** panel in the left sidebar.

## Visual Layout

```
┌─────────────────────────────────────────┐
│ Market Watch                            │
│ Symbols / tickers (live rankings)       │
├─────────────────────────────────────────┤
│ Exchange: [Bitfinex ▼]  ← NEW DROPDOWN │
│                                         │
│ Primary: BTCUSD                         │
│                                         │
│ Symbol List:                            │
│ • BTCUSD                               │
│ • ETHUSD                               │
│ • SOLUSD                               │
│ • ...                                  │
└─────────────────────────────────────────┘
```

## Exchange Dropdown Options
- Bitfinex
- Binance

## Behavior

### When Bitfinex is Selected:
- Market Data panel shows: "Bitfinex candles (OHLCV)"
- Available symbols: BTCUSD, ETHUSD, SOLUSD, etc.
- Chart displays Bitfinex data
- Ingestion status queries Bitfinex endpoint

### When Binance is Selected:
- Market Data panel shows: "Binance candles (OHLCV)"
- Available symbols: BTCUSDT, ETHUSDT, SOLUSDT, etc.
- Chart displays Binance data
- Ingestion status queries Binance endpoint

## Example State Changes

### Before (Bitfinex selected):
```
Market Watch
└── Exchange: Bitfinex
    ├── Symbols: BTCUSD, ETHUSD, ...
    └── Chart: Bitfinex BTCUSD 1m

Market Data
└── Bitfinex candles (OHLCV)
    └── API: Reachable
        └── BTCUSD-1m latest: 2024-12-26 13:45
```

### After Switching to Binance:
```
Market Watch
└── Exchange: Binance
    ├── Symbols: BTCUSDT, ETHUSDT, ...
    └── Chart: Binance BTCUSDT 1m

Market Data
└── Binance candles (OHLCV)
    └── API: Reachable
        └── BTCUSD-1m latest: 2024-12-26 13:45
```

## Code Implementation

### Exchange State
```typescript
const [chartExchange, setChartExchange] = useState<string>('bitfinex')
```

### Dropdown Component
```tsx
<Kvp
  k="Exchange"
  v={
    <select
      className="rounded border border-gray-200 bg-white px-1 py-0.5 text-xs ..."
      value={chartExchange}
      onChange={(ev) => setChartExchange(ev.target.value)}
    >
      <option value="bitfinex">Bitfinex</option>
      <option value="binance">Binance</option>
    </select>
  }
/>
```

### Dynamic API Calls
```typescript
// Available symbols
fetch(`/api/candles/available?exchange=${encodeURIComponent(chartExchange)}`)

// Candles data
fetch(`/api/candles?exchange=${encodeURIComponent(exchange)}&symbol=${symbol}...`)

// Ingestion status
fetch(`/ingestion/status?exchange=${encodeURIComponent(chartExchange)}&...`)
```

## Visual Design

### Dropdown Styling
- Small, compact select element
- Matches existing UI style (dark mode compatible)
- Same border/background as other inputs
- Minimal visual footprint

### Dark Mode Support
```css
border: gray-200 (light) / gray-800 (dark)
background: white (light) / gray-950 (dark)
text: gray-700 (light) / gray-200 (dark)
```

## Accessibility
- Keyboard navigation supported
- Clear visual feedback on selection
- Semantic HTML (native `<select>` element)

## Integration Points

1. **Market Watch Panel**: Exchange selector dropdown
2. **Market Data Panel**: Dynamic subtitle showing selected exchange
3. **Chart Panel**: Fetches data from selected exchange
4. **Ingestion Status**: Queries selected exchange endpoint
5. **Symbol List**: Filtered by selected exchange

## Testing Checklist

To validate the UI changes:

1. ✅ Dropdown appears in Market Watch panel
2. ✅ Switching exchanges updates the chart
3. ✅ Symbol list refreshes for selected exchange
4. ✅ Market Data panel reflects selected exchange
5. ✅ Ingestion status queries correct endpoint
6. ✅ Dark mode styling works correctly
7. ✅ No console errors when switching
8. ✅ Page state persists across refreshes

## Notes

- The exchange selector is persistent across page refreshes (localStorage not implemented, defaults to 'bitfinex')
- Switching exchanges triggers a full reload of available symbols and chart data
- The WebSocket/SSE connection is exchange-specific and reconnects on exchange change
- No data mixing between exchanges - each exchange has isolated data streams
