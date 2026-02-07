import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxy = {
  target: 'http://127.0.0.1:8000',
  changeOrigin: true,
  // FastAPI routes are mounted without an /api prefix.
  rewrite: (path: string) => path.replace(/^\/api/, ''),
}

const wsProxy = {
  target: 'ws://127.0.0.1:8000',
  ws: true,
}

const sharedProxy = {
  '/api': apiProxy,
  '/ws': wsProxy,
  '/healthz': 'http://127.0.0.1:8000',
  '/system': 'http://127.0.0.1:8000',
  '/candles': 'http://127.0.0.1:8000',
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5176,
    strictPort: true,
    proxy: sharedProxy,
  },
  preview: {
    proxy: sharedProxy,
  },
})
