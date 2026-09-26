import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    port: 3001, // web-kb 用 3000，统一外壳用 3001，避免本地同时起时冲突
    // USE_MOCK=false 时，前端 /api/* 经此代理到本地 FastAPI（python -m api.server）
    proxy: {
      "/api": {
        target: process.env.ARK_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
