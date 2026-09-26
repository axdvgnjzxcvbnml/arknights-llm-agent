import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

// https://vite.dev/config/
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    port: 3001, // web-kb 用 3000，统一外壳用 3001，避免本地同时起时冲突
    // USE_MOCK=false 时，前端 /api/* 与 /ws/* 经此代理到本地 FastAPI（python -m api.server）
    proxy: {
      "/api": {
        target: process.env.ARK_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: process.env.ARK_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true, // WebSocket 代理（/ws/live 实时对局推送）
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // Vitest 配置（任务3：前端单元测试）
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
})
