/** 通用格式化与小工具。所有展示用的数字/时间都从这里走，避免各处写法不一。 */

/** snake_case -> camelCase（深层）。用于兼容 FastAPI 直接返回 pydantic 模型的情况 */
export function camelizeDeep(value) {
  if (Array.isArray(value)) return value.map(camelizeDeep)
  if (value && typeof value === 'object' && value.constructor === Object) {
    const out = {}
    for (const [k, v] of Object.entries(value)) {
      const parts = String(k).split('_')
      const key = parts[0] + parts.slice(1).map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join('')
      out[key] = camelizeDeep(v)
    }
    return out
  }
  return value
}

export function isNil(v) {
  return v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v))
}

/** 毫秒：0.087 -> "0.1ms"，1234.5 -> "1.24s"（超过 1s 换单位，避免一长串 0） */
export function fmtMs(ms, digits = 1) {
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(2)}s`
  return `${n.toFixed(digits)}ms`
}

/** 秒：保留 1~3 位有效小数 */
export function fmtSec(sec, digits = 1) {
  const n = Number(sec)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(digits)}s`
}

/** 带符号数值：+100.0 / -30.0 / 0 */
export function fmtSigned(n, digits = 1) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  const s = v.toFixed(digits)
  return v > 0 ? `+${s}` : s
}

/** 0~1 -> 百分比 */
export function fmtPct(ratio, digits = 0) {
  const v = Number(ratio)
  if (!Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

export function fmtNum(n, digits = 0) {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return v.toFixed(digits)
}

/** 时间戳（秒）-> 本地时间字符串 */
export function fmtTs(ts) {
  const n = Number(ts)
  if (!Number.isFinite(n) || n <= 0) return '—'
  const d = new Date(n > 1e12 ? n : n * 1000)
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** 数值 -> 颜色（正绿负红，0 中性） */
export function rewardColor(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || n === 0) return '#94a3b8'
  return n > 0 ? '#34d399' : '#fb7185'
}

/** 把 "a=1 b=2" 之类的对象转成有序数组，便于渲染条形图 */
export function entries(obj) {
  return Object.entries(obj || {}).filter(([, v]) => v !== null && v !== undefined)
}

/** 求数组最大值，全 0 时返回 0（条形图分母兜底，避免除零） */
export function safeMax(values) {
  const nums = values.map(Number).filter(Number.isFinite)
  return nums.length ? Math.max(...nums, 0) : 0
}

export function clamp(v, min, max) {
  return Math.min(Math.max(Number(v) || 0, min), max)
}

/** 键盘事件里忽略输入框内的按键，避免打字时误触翻页 */
export function isTypingTarget(el) {
  if (!el) return false
  const tag = String(el.tagName || '').toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable
}
