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
