import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// FastAPI backend defaults to port 8000 (see docs/PORTS.md).
const BACKEND_HTTP = 'http://127.0.0.1:8000'
const BACKEND_WS = 'ws://127.0.0.1:8000'
const IS_DEV = process.env.NODE_ENV !== 'production'
// Disable SSL verification only in local development with self-signed certs.
const REST_PROXY = { target: BACKEND_HTTP, changeOrigin: true, secure: !IS_DEV }

const sharedProxy = {
  '/api': {
    ...REST_PROXY,
    // Frontend uses /api as a convention; backend routes are mounted without it.
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
