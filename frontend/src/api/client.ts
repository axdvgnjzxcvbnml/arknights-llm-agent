import { deepCamelize } from "@/lib/utils"

/**
 * 统一 API 客户端。
 * - VITE_USE_MOCK !== "false"（默认）：读 public/mock/<name>.json，不依赖后端；
 * - VITE_USE_MOCK=false：请求同源 /api/*（dev 经 vite proxy 到 FastAPI，见 vite.config）。
 * 与 web-kb 的 USE_MOCK 口径一致，合并后共用。
 *
 * 所有返回统一经 deepCamelize，组件只接收 camelCase。
 */

export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK !== "false"
const API_BASE = import.meta.env.VITE_API_BASE ?? ""

// 用根绝对路径定位 mock，避免 BrowserRouter 深路由（/kb/rag 等）下
// 相对 "./mock" 被 pushState 后的 document URL 解析成 /kb/mock。
// base 为相对（"./"）时按站点根 "/" 归一；base 为绝对子路径（"/sub/"）时沿用。
const ROOT_BASE = import.meta.env.BASE_URL.startsWith(".")
  ? "/"
  : import.meta.env.BASE_URL

async function loadMock<T>(name: string): Promise<T> {
  const url = `${window.location.origin}${ROOT_BASE}mock/${name}.json`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`mock 数据缺失: ${url} (${res.status})`)
  return deepCamelize<T>(await res.json())
}

async function getApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`API ${path} 失败: ${res.status}`)
  return deepCamelize<T>(await res.json())
}

/** mock 文件名 / 真实路径 二选一。 */
export async function fetchJson<T>(mockName: string, realPath: string): Promise<T> {
  return USE_MOCK ? loadMock<T>(mockName) : getApi<T>(realPath)
}

export { API_BASE }
