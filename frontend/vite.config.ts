import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_HTTP = 'http://127.0.0.1:8000'
const BACKEND_WS = 'ws://127.0.0.1:8000'
const REST_PROXY = { target: BACKEND_HTTP, changeOrigin: true }

const sharedProxy = {
  '/api': {
    ...REST_PROXY,
    // FastAPI routes are mounted without an /api prefix.
    rewrite: (path: string) => path.replace(/^\/api/, ''),
  },
  '/ws': {
    target: BACKEND_WS,
    ws: true,
    changeOrigin: true,
  },
  '/healthz': REST_PROXY,
  '/system': REST_PROXY,
  '/candles': REST_PROXY,
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
