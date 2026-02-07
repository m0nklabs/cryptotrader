import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// All backend routes that need proxying (order matters: specific before general)
const backendProxy = {
  // NOTE: wallets-data service (port 8101) not yet running
  // Uncomment when wallets-data is deployed:
  // '/api/wallet': {
  //   target: 'http://127.0.0.1:8101',
  //   rewrite: (path: string) => path.replace(/^\/api\/wallet/, ''),
  // },
  '/api': {
    target: 'http://127.0.0.1:8000',
    rewrite: (path: string) => path.replace(/^\/api/, ''),
    ws: true,
  },
  // Direct backend routes (no /api prefix)
  '/healthz': 'http://127.0.0.1:8000',
  '/health': 'http://127.0.0.1:8000',
  '/system': 'http://127.0.0.1:8000',
  '/candles': 'http://127.0.0.1:8000',
  '/ingestion': 'http://127.0.0.1:8000',
  '/signals': 'http://127.0.0.1:8000',
  '/positions': 'http://127.0.0.1:8000',
  '/market-watch': 'http://127.0.0.1:8000',
  '/gaps': 'http://127.0.0.1:8000',
  '/ratelimit': 'http://127.0.0.1:8000',
  '/arbitrage': 'http://127.0.0.1:8000',
  '/notifications': 'http://127.0.0.1:8000',
  '/export': 'http://127.0.0.1:8000',
  '/research': 'http://127.0.0.1:8000',
  '/orders': 'http://127.0.0.1:8000',
  '/ws': {
    target: 'http://127.0.0.1:8000',
    ws: true,
  },
} as Record<string, string | { target: string; rewrite?: (path: string) => string; ws?: boolean }>

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5176,
    strictPort: true,
    proxy: backendProxy,
  },
  preview: {
    proxy: backendProxy,
  },
})
