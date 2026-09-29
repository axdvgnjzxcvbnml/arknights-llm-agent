import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/** 单个 snake/kebab 键转 camelCase：latency_ms_p50 -> latencyMsP50。 */
export function camelizeKey(key: string): string {
  return key.replace(/[_-]([a-z0-9])/g, (_, c: string) => c.toUpperCase())
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

/**
 * 深度把对象所有键从 snake_case 转成 camelCase（数组递归）。
 * 后端返回统一走这里，组件层只见 camelCase。null/undefined 原样返回。
 */
export function deepCamelize<T = unknown>(input: unknown): T {
  if (Array.isArray(input)) {
    return input.map((v) => deepCamelize(v)) as unknown as T
  }
  if (isPlainObject(input)) {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(input)) {
      out[camelizeKey(k)] = deepCamelize(v)
    }
    return out as T
  }
  return input as T
}

/** ISO 时间 -> "MM-DD HH:mm:ss"；非法输入返回占位。 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  const p = (n: number) => String(n).padStart(2, "0")
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes(),
  )}:${p(d.getSeconds())}`
}

/** 毫秒耗时 -> "4m12s" / "830ms"。 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—"
  if (ms < 1000) return `${Math.round(ms)}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  return `${m}m${Math.round(s - m * 60)}s`
}

/** 0..1 -> 百分比字符串（与 RAG score 量纲一致：后端 1-cosine，0-1）。 */
export function asPercent(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return "—"
  return `${(v * 100).toFixed(digits)}%`
}

// ---- web/ 移植的格式化工具 ----
export const camelizeDeep = deepCamelize


// ---- web/ 移植的格式化工具 ----
export function isNil(v: unknown): boolean {
  return v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v))
}
export function fmtMs(ms: number, digits = 1): string {
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(2)}s`
  return `${n.toFixed(digits)}ms`
}
export function fmtSec(sec: number, digits = 1): string {
  const n = Number(sec)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(digits)}s`
}
export function fmtSigned(n: number, digits = 1): string {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  const s = v.toFixed(digits)
  return v > 0 ? `+${s}` : s
}
export function fmtPct(ratio: number, digits = 0): string {
  const v = Number(ratio)
  if (!Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}
export function fmtNum(n: number, digits = 0): string {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}
export function fmtTs(ts: number): string {
  const n = Number(ts)
  if (!Number.isFinite(n) || n <= 0) return '—'
  const d = new Date(n > 1e12 ? n : n * 1000)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
export function rewardColor(v: number): string {
  const n = Number(v)
  if (!Number.isFinite(n) || n === 0) return '#94a3b8'
  return n > 0 ? '#34d399' : '#fb7185'
}
export function entries(obj: Record<string, unknown>): [string, unknown][] {
  return Object.entries(obj || {}).filter(([, v]) => v !== null && v !== undefined)
}
export function safeMax(values: number[]): number {
  const nums = values.map(Number).filter(Number.isFinite)
  return nums.length ? Math.max(...nums, 0) : 0
}
export function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(Number(v) || 0, min), max)
}
export function isTypingTarget(el: HTMLElement | null): boolean {
  if (!el) return false
  const tag = String(el.tagName || '').toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable
}
