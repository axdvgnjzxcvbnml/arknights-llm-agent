import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

// vitest 启动时强制 NODE_ENV=test：部分环境（CI、容器镜像）预设 NODE_ENV=production，
// 会让 React 加载生产构建、不暴露 act()，所有 render/renderHook 测试直接报
// "React.act is not a function"。只在 vitest 进程里改，`vite build` 不受影响。
if (process.env.VITEST) {
  process.env.NODE_ENV = "test"
}

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
    // 某些环境（含 CI 与部分容器镜像）预设 NODE_ENV=production，React 会加载生产构建、
    // 不暴露 act()，导致所有 render/renderHook 测试报 "React.act is not a function"。
    // 这里显式固定为 test，让 `npm test` 不受外部 NODE_ENV 影响。
    env: { NODE_ENV: "test" },
  },
})
