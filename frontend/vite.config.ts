import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5176,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/healthz': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/system': 'http://127.0.0.1:8000',
      '/candles': 'http://127.0.0.1:8000',
    },
  },
  preview: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/healthz': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/system': 'http://127.0.0.1:8000',
      '/candles': 'http://127.0.0.1:8000',
    },
  },
})
