import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5176,
    strictPort: true,
    proxy: {
      // NOTE: wallets-data service (port 8101) not yet running
      // Uncomment when wallets-data is deployed:
      // '/api/wallet': {
      //   target: 'http://127.0.0.1:8101',
      //   rewrite: (path) => path.replace(/^\/api\/wallet/, ''),
      // },
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/healthz': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/system': 'http://127.0.0.1:8000',
      '/candles': 'http://127.0.0.1:8000',
      '/ingestion': 'http://127.0.0.1:8000',
    },
  },
  preview: {
    proxy: {
      // NOTE: wallets-data service (port 8101) not yet running
      // Uncomment when wallets-data is deployed:
      // '/api/wallet': {
      //   target: 'http://127.0.0.1:8101',
      //   rewrite: (path) => path.replace(/^\/api\/wallet/, ''),
      // },
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/healthz': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/system': 'http://127.0.0.1:8000',
      '/candles': 'http://127.0.0.1:8000',
      '/ingestion': 'http://127.0.0.1:8000',
    },
  },
})
