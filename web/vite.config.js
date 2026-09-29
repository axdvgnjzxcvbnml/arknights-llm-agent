import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 后端 FastAPI 上线后：把 VITE_USE_MOCK 设为 false，并用下面的 proxy 转发 /api，
// 即可零改动切到真实接口（前端只通过 src/api.js 取数）。
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
