// @ts-nocheck
/**
 * 数据访问层（前端唯一取数入口）。
 *
 * 设计目标：**后端 API 上线时，业务组件一行都不用改**。
 * - 现在：USE_MOCK=true，从 web/src/mock/*.json 读静态数据（由 scripts/export_mock.py 生成）；
 * - 以后：USE_MOCK=false，同样的函数签名改成请求 FastAPI：
 *     GET /api/episodes            -> 对局列表
 *     GET /api/episode/{id}        -> 对局报告（汇总 + 奖励）
 *     GET /api/episode/{id}/steps  -> 每步详情
 *
 * 约定的返回结构（mock 与真实后端一致）：
 *   listEpisodes()        -> { schemaVersion, generatedAt, episodes: [EpisodeSummary] }
 *   fetchEpisode(id)      -> EpisodeSummary & { reward, totals, map, ... }
 *   fetchEpisodeSteps(id) -> [StepDto]
 *   fetchEpisodeFull(id)  -> { episode, steps }   // 回放界面用，内部并发拉上面两个
 *
 * 真实后端若直接序列化 pydantic 模型（snake_case），normalize* 会自动转成前端用的
 * camelCase；已经是 camelCase 的响应也原样可用。
 */
import { API_BASE, MOCK_LATENCY_MS, REQUEST_TIMEOUT_MS, USE_MOCK } from '@/api/client'
import { camelizeDeep } from '@/lib/utils'

import mockEpisodes from '@/mock/episodes.json'
import mockRawLogs from '@/mock/rawLogs.json'
import mockEp38Win from '@/mock/ep-3-8-win.json'
import mockEp38Lose from '@/mock/ep-3-8-lose.json'

/** mock 数据表：id -> 完整对局文档。新增 mock 对局只要在这里登记一行 */
const MOCK_STORE = {
  'ep-3-8-win': mockEp38Win,
  'ep-3-8-lose': mockEp38Lose,
}

/** 真实接口路径（集中管理，便于后端对齐 / 联调时排查） */
export const endpoints = {
  listEpisodes: () => `${API_BASE}/api/episodes`,
  episode: (id) => `${API_BASE}/api/episode/${encodeURIComponent(id)}`,
  steps: (id) => `${API_BASE}/api/episode/${encodeURIComponent(id)}/steps`,
  rawLogs: () => `${API_BASE}/api/logs`,
}

export const dataSource = {
  mode: USE_MOCK ? 'mock' : 'api',
  base: USE_MOCK ? 'static:web/src/mock' : API_BASE || 'same-origin',
}

// ------------------------------------------------------------------ 底层请求
class ApiError extends Error {
  constructor(message, { status = 0, url = '', cause = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
    this.cause = cause
  }
}

async function http(url, { timeoutMs = REQUEST_TIMEOUT_MS } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { Accept: 'application/json' },
    })
    if (!res.ok) {
      throw new ApiError(`接口返回 ${res.status} ${res.statusText || ''}`.trim(),
        { status: res.status, url })
    }
    return await res.json()
  } catch (err) {
    if (err instanceof ApiError) throw err
    const reason = err?.name === 'AbortError' ? `请求超时（>${timeoutMs}ms）` : (err?.message || '网络错误')
    throw new ApiError(reason, { url, cause: err })
  } finally {
    clearTimeout(timer)
  }
}

/** mock 模式下的一点延迟：让 loading 态真实可见，也避免"秒开"掩盖异步问题 */
function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function mockDoc(id) {
  const doc = MOCK_STORE[id]
  if (!doc) {
    throw new ApiError(`mock 数据里没有对局 ${id}（可用：${Object.keys(MOCK_STORE).join(', ')}）`,
      { url: `mock://${id}` })
  }
  return doc
}

// ------------------------------------------------------------------ 归一化
/**
 * 后端 DTO -> 前端视图模型。
 * 现在基本是恒等变换（export_mock.py 已按 camelCase 导出），保留这层是为了：
 *   1. 兼容 FastAPI 直接返回 pydantic snake_case 的情况；
 *   2. 给字段缺失兜底（例如没有奖励结算的日志），组件里就不用到处判空。
 */
export function normalizeEpisode(raw) {
  const ep = camelizeDeep(raw || {})
  return {
    ...ep,
    outcome: ep.outcome || 'aborted',
    outcomeLabel: ep.outcomeLabel || ep.outcome || '未知',
    stepCount: ep.stepCount ?? (ep.steps ? ep.steps.length : 0),
    reward: {
      total: 0, winBonus: 0, leakPenalty: 0, overcostPenalty: 0,
      leaked: 0, overcostSec: 0, lifeStart: null, lifeEnd: null,
      summaryLine: '', items: [],
      ...(ep.reward || {}),
    },
    totals: {
      actionsTotal: 0, actionsSucceeded: 0, actionsFailed: 0,
      avgConfidence: 0, latencySumMs: {},
      ...(ep.totals || {}),
    },
    map: ep.map || { cols: 0, rows: 0, cells: [] },
  }
}

export function normalizeStep(raw, index = 0) {
  const s = camelizeDeep(raw || {})
  return {
    index,
    step: s.step ?? index + 1,
    elapsedSec: s.elapsedSec ?? 0,
    state: {
      stageId: '', timingSource: 'none', cost: null, lifePoints: null,
      deployUsed: null, deployLimit: null, operatorCards: [], deployed: [],
      skills: [], enemiesOnField: [], spawnPlan: [], occupiedCells: [],
      notes: [], vlm: null, stateText: '',
      ...(s.state || {}),
    },
    knowledge: { query: '', contextText: '', citations: [], ...(s.knowledge || {}) },
    reasoning: {
      summary: '', analysis: [], consideredActions: [], risks: [],
      ...(s.reasoning || {}),
    },
    decision: { confidence: 0, thinker: '', thoughtMs: 0, plan: { actions: [] }, ...(s.decision || {}) },
    bridge: s.bridge || null,
    command: s.command || null,
    execute: s.execute || null,
    reflection: s.reflection || null,
    after: { cost: null, life: null, ...(s.after || {}) },
    reward: { stepReward: 0, items: [], ...(s.reward || {}) },
    evidence: Array.isArray(s.evidence) ? s.evidence : [],
    latencyMs: s.latencyMs || {},
  }
}

// ------------------------------------------------------------------ 对外 API
/** 对局列表（顶部切换器用） */
export async function listEpisodes() {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    return camelizeDeep(mockEpisodes)
  }
  return camelizeDeep(await http(endpoints.listEpisodes()))
}

/** GET /api/episode/{id} —— 对局报告（汇总 + 奖励 + 地图拓扑） */
export async function fetchEpisode(id) {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    return normalizeEpisode(mockDoc(id).episode)
  }
  return normalizeEpisode(await http(endpoints.episode(id)))
}

/** GET /api/episode/{id}/steps —— 每步详情 */
export async function fetchEpisodeSteps(id) {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    const steps = mockDoc(id).steps || []
    return steps.map(normalizeStep)
  }
  const raw = await http(endpoints.steps(id))
  const list = Array.isArray(raw) ? raw : (raw?.steps || raw?.items || [])
  return list.map(normalizeStep)
}

/**
 * 回放界面实际用的入口：并发拉「对局报告 + 每步详情」再合并。
 * mock 模式下直接读同一份文档，语义等价。
 */
export async function fetchEpisodeFull(id) {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    const doc = mockDoc(id)
    return {
      episode: normalizeEpisode(doc.episode),
      steps: (doc.steps || []).map(normalizeStep),
    }
  }
  const [episode, steps] = await Promise.all([fetchEpisode(id), fetchEpisodeSteps(id)])
  return { episode, steps }
}

/** 原始文本日志（results/*.txt 同源内容），后端未提供时回落到 mock */
export async function fetchRawLogs() {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    return camelizeDeep(mockRawLogs)
  }
  try {
    return camelizeDeep(await http(endpoints.rawLogs()))
  } catch (err) {
    // 原始日志属于附加能力，后端没实现时不该让整个界面挂掉
    console.warn('[api] /api/logs 不可用，回落到本地 mock 日志：', err.message)
    return camelizeDeep(mockRawLogs)
  }
}

export { ApiError, MOCK_STORE }
