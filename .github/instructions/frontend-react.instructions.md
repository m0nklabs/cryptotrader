---
applyTo: "frontend/**/*.{ts,tsx}"
---

## Frontend React/TypeScript Requirements

When working on frontend code, follow these guidelines:

### Stack
- **React 18+** with TypeScript
- **Vite** for bundling (dev server on port 5176)
- **Tailwind CSS** with dark mode default
- **React Query** for server state
- **Zustand** for client state

### Code Standards

1. **TypeScript strict mode** - All code must be properly typed
2. **Functional components** - Use hooks, no class components
3. **Custom hooks** - Extract reusable logic into `use*` hooks
4. **Error boundaries** - Wrap major sections with error boundaries

### Styling
- Use Tailwind utility classes
- Dark mode first: use `dark:` variants for light mode overrides
- Small font sizes (MT4/5 inspired UI)
- Collapsible panels with sticky header/footer

### State Management
```typescript
// Server state - React Query
const { data, isLoading } = useQuery({
  queryKey: ['ohlcv', symbol, exchange],
  queryFn: () => fetchOHLCV(symbol, exchange),
});

// Client state - Zustand
const useStore = create((set) => ({
  selectedExchange: 'binance',
  setExchange: (exchange) => set({ selectedExchange: exchange }),
}));
```

### API Calls
- Use `fetch` or axios with proper error handling
- Base URL from environment variables
- Handle loading, error, and empty states

### What NOT to do:
- Don't use `any` type - define proper interfaces
- Don't mutate state directly
- Don't use inline styles (use Tailwind)

### Chart Library
- Use **lightweight-charts** (TradingView) for candlestick/price charts
- Import from `lightweight-charts` package
- Dark theme by default with `#1a1a2e` backgrounds

### SSE/WebSocket Streaming
```typescript
// Server-Sent Events pattern (candle streaming)
const eventSource = new EventSource(`/api/candles/stream?symbol=${symbol}`);
eventSource.onmessage = (event) => {
  const candle = JSON.parse(event.data);
  // Update chart...
};
```

### AI Module Components

When building AI-related frontend features:

- **API module**: `frontend/src/api/ai.ts` — calls to `/api/ai/*` endpoints
- **Store**: `frontend/src/stores/aiStore.ts` — Zustand store for AI config state
- **Components**: `frontend/src/components/AiConfigPanel.tsx` — role/provider/prompt management
- Always type API responses with proper interfaces matching backend Pydantic models

```typescript
// AI API response types
interface ProviderHealth {
  name: string;
  healthy: boolean;
  model: string;
  lastChecked: string;
  message: string;
}

interface RoleConfig {
  name: string;
  provider: string;
  model: string;
  weight: number;
  enabled: boolean;
  temperature: number;
  maxTokens: number;
}
```
