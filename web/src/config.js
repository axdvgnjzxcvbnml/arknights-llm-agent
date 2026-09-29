/**
 * 运行期配置：全部走 Vite 环境变量（VITE_ 前缀），不硬编码。
 *
 * 三种典型用法：
 *   1. 纯 mock（默认）              npm run dev
 *   2. 连本地 FastAPI               VITE_USE_MOCK=false npm run dev
 *   3. 连指定后端                   VITE_USE_MOCK=false VITE_API_BASE=http://10.0.0.5:8000 npm run build
 *
 * 也可以写进 web/.env.local（Vite 自动加载，不入库）：
 *   VITE_USE_MOCK=false
 *   VITE_API_BASE=http://127.0.0.1:8000
 */
const env = (typeof import.meta !== 'undefined' && import.meta.env) || {}

function bool(name, fallback) {
  const raw = env[name]
  if (raw === undefined || raw === '') return fallback
  return String(raw).toLowerCase() !== 'false' && String(raw) !== '0'
}

function num(name, fallback) {
  const v = Number(env[name])
  return Number.isFinite(v) ? v : fallback
}

/** true = 用 web/src/mock 下的静态数据；false = 请求真实后端 */
export const USE_MOCK = bool('VITE_USE_MOCK', true)

/** 后端基地址。留空表示同源（配合 vite.config.js 的 /api 代理最省事） */
export const API_BASE = String(env.VITE_API_BASE || '').replace(/\/+$/, '')

/** mock 模式下模拟的网络延迟（毫秒），用来验证 loading 态；设为 0 可关掉 */
export const MOCK_LATENCY_MS = num('VITE_MOCK_LATENCY_MS', 120)

/** 请求超时（毫秒），超时后按失败处理并给出可重试的错误 */
export const REQUEST_TIMEOUT_MS = num('VITE_REQUEST_TIMEOUT_MS', 15000)

export const DATA_SOURCE = {
  mode: USE_MOCK ? 'mock' : 'api',
  base: USE_MOCK ? 'web/src/mock/*.json' : API_BASE || '(同源 /api)',
}
