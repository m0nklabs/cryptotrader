import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_PORT = process.env.PORT || '50000'
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || '50176')
const BACKEND_HTTP = process.env.VITE_API_PROXY_TARGET || `http://127.0.0.1:${BACKEND_PORT}`
const BACKEND_WS = process.env.VITE_WS_PROXY_TARGET || BACKEND_HTTP.replace(/^http/, 'ws')
// Set VITE_DISABLE_SSL_VERIFY=true for self-signed certs in local dev.
const DISABLE_SSL_VERIFY = process.env.VITE_DISABLE_SSL_VERIFY === 'true'
const REST_PROXY = { target: BACKEND_HTTP, changeOrigin: true, secure: !DISABLE_SSL_VERIFY }

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
  '/health': REST_PROXY,
  '/system': REST_PROXY,
  '/candles': REST_PROXY,
  '/dossier': REST_PROXY,
  '/signals': REST_PROXY,
  '/orders': REST_PROXY,
  '/positions': REST_PROXY,
  '/ingestion': REST_PROXY,
  '/market-cap': REST_PROXY,
  '/wallets': REST_PROXY,
  '/opportunities': REST_PROXY,
  '/backtest': REST_PROXY,
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: FRONTEND_PORT,
    strictPort: true,
    proxy: sharedProxy,
  },
  preview: {
    host: true,
    port: FRONTEND_PORT,
    strictPort: true,
    proxy: sharedProxy,
  },
})
