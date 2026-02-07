import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// FastAPI backend defaults to port 8000 (see docs/PORTS.md in repo). Legacy helper script ran on 8787.
const BACKEND_HTTP = 'http://127.0.0.1:8000'
const BACKEND_WS = 'ws://127.0.0.1:8000'
// Set VITE_DISABLE_SSL_VERIFY=true for self-signed certs in local dev.
const DISABLE_SSL_VERIFY = process.env.VITE_DISABLE_SSL_VERIFY === 'true'
// SSL verification is disabled only when VITE_DISABLE_SSL_VERIFY=true.
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
