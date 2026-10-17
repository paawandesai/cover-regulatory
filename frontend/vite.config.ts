import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// The API runs separately (uvicorn on :8000); the dev server proxies /api to it.
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.API_URL ?? 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  worker: { format: 'es' },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'] },
})
