/**
 * 数据访问层（对局回放页的唯一取数入口）。
 *
 * 设计目标：**后端 API 上线时，业务组件一行都不用改**。
 * - USE_MOCK=true（默认）：读 `src/mock/*.json`（由 web/scripts/export_mock.py 生成）；
 * - USE_MOCK=false：请求 FastAPI
 *     GET /api/episodes            -> 对局列表
 *     GET /api/episode/{id}        -> 对局报告（汇总 + 奖励）
 *     GET /api/episode/{id}/steps  -> 每步详情
 *
 * 类型口径：入参一律 `unknown`（wire 格式，snake_case 或 camelCase 都可能），
 * 出参一律 `src/types/episode.ts` 里的 *Dto（camelCase、字段兜底完成），
 * 组件层只见 Dto，不需要判空、也不会碰到 snake_case。
 *
 * ⚠️ 已知契约缺口见 GitHub Issue #1/#2/#3：API 模式下 steps 里目前没有结构化
 * GameState（只有 trace.state_excerpt 文本）、对局级没有地图拓扑，
 * 相关字段 normalize* 会兜成空数组/null，组件走空态分支。
 */
import { API_BASE, MOCK_LATENCY_MS, REQUEST_TIMEOUT_MS, USE_MOCK } from '@/api/client'
import { camelizeDeep } from '@/lib/utils'
import type {
  EpisodeDto,
  EpisodeFull,
  EpisodeIndex,
  MockEpisodeDoc,
  RawLogEntry,
  StepDto,
} from '@/types/episode'

import mockEpisodes from '@/mock/episodes.json'
import mockRawLogs from '@/mock/rawLogs.json'
import mockEp38Win from '@/mock/ep-3-8-win.json'
import mockEp38Lose from '@/mock/ep-3-8-lose.json'

/** wire 数据在归一化前的松散视图：边界处允许 any，出口处严格 Dto */
type Raw = Record<string, any>

/** mock 数据表：id -> 完整对局文档。新增 mock 对局只要在这里登记一行 */
const MOCK_STORE: Record<string, MockEpisodeDoc> = {
  'ep-3-8-win': mockEp38Win,
  'ep-3-8-lose': mockEp38Lose,
}

/** 真实接口路径（集中管理，便于后端对齐 / 联调时排查） */
export const endpoints = {
  listEpisodes: (): string => `${API_BASE}/api/episodes`,
  episode: (id: string): string => `${API_BASE}/api/episode/${encodeURIComponent(id)}`,
  steps: (id: string): string => `${API_BASE}/api/episode/${encodeURIComponent(id)}/steps`,
  rawLogs: (): string => `${API_BASE}/api/logs`,
}

export const dataSource: { mode: 'mock' | 'api'; base: string } = {
  mode: USE_MOCK ? 'mock' : 'api',
  base: USE_MOCK ? 'static:src/mock' : API_BASE || 'same-origin',
}

// ------------------------------------------------------------------ 底层请求
export interface ApiErrorOptions {
  status?: number
  url?: string
  cause?: unknown
}

export class ApiError extends Error {
  status: number
  url: string
  override cause?: unknown

  constructor(message: string, { status = 0, url = '', cause = null }: ApiErrorOptions = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
    this.cause = cause
  }
}

interface HttpOptions {
  timeoutMs?: number
}

async function http<T = unknown>(url: string, { timeoutMs = REQUEST_TIMEOUT_MS }: HttpOptions = {}): Promise<T> {
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
    return (await res.json()) as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    const e = err as { name?: string; message?: string }
    const reason = e?.name === 'AbortError' ? `请求超时（>${timeoutMs}ms）` : (e?.message || '网络错误')
    throw new ApiError(reason, { url, cause: err })
  } finally {
    clearTimeout(timer)
  }
}

/** mock 模式下的一点延迟：让 loading 态真实可见，也避免"秒开"掩盖异步问题 */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function mockDoc(id: string): MockEpisodeDoc {
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
 * mock 数据基本是恒等变换（export_mock.py 已按 camelCase 导出），保留这层是为了：
 *   1. 兼容 FastAPI 直接返回 pydantic snake_case 的情况；
 *   2. 给字段缺失兜底（Issue #1/#2/#3 那几类），组件里就不用到处判空。
 */
export function normalizeEpisode(raw: unknown): EpisodeDto {
  const ep = camelizeDeep<Raw>(raw ?? {})
  return {
    ...ep,
    id: ep.id ?? '',
    stageId: ep.stageId ?? '',
    backend: ep.backend ?? 'unknown',
    outcome: ep.outcome || 'aborted',
    outcomeLabel: ep.outcomeLabel || ep.outcome || '未知',
    stepCount: ep.stepCount ?? (Array.isArray(ep.steps) ? ep.steps.length : 0),
    durationSec: Number(ep.durationSec ?? 0),
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
  } as EpisodeDto
}

export function normalizeStep(raw: unknown, index = 0): StepDto {
  const s = camelizeDeep<Raw>(raw ?? {})
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
  } as StepDto
}

// ------------------------------------------------------------------ 对外 API
/** 对局列表（顶部切换器用） */
export async function listEpisodes(): Promise<EpisodeIndex> {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    return camelizeDeep<EpisodeIndex>(mockEpisodes)
  }
  return camelizeDeep<EpisodeIndex>(await http(endpoints.listEpisodes()))
}

/** GET /api/episode/{id} —— 对局报告（汇总 + 奖励 + 地图拓扑） */
export async function fetchEpisode(id: string): Promise<EpisodeDto> {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    return normalizeEpisode(mockDoc(id).episode)
  }
  return normalizeEpisode(await http(endpoints.episode(id)))
}

/** GET /api/episode/{id}/steps —— 每步详情 */
export async function fetchEpisodeSteps(id: string): Promise<StepDto[]> {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    const steps = mockDoc(id).steps || []
    return steps.map((s, i) => normalizeStep(s, i))
  }
  const raw = await http<Raw>(endpoints.steps(id))
  const list: unknown[] = Array.isArray(raw) ? raw : (raw?.steps || raw?.items || [])
  return list.map((s, i) => normalizeStep(s, i))
}

/**
 * 回放页实际用的入口：并发拉「对局报告 + 每步详情」再合并。
 * mock 模式下直接读同一份文档，语义等价。
 */
export async function fetchEpisodeFull(id: string): Promise<EpisodeFull> {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    const doc = mockDoc(id)
    return {
      episode: normalizeEpisode(doc.episode),
      steps: (doc.steps || []).map((s, i) => normalizeStep(s, i)),
    }
  }
  const [episode, steps] = await Promise.all([fetchEpisode(id), fetchEpisodeSteps(id)])
  return { episode, steps }
}

/** 原始文本日志（results/*.txt 同源内容）。后端未提供（Issue #6，实测 404）时回落到 mock */
export async function fetchRawLogs(): Promise<RawLogEntry[]> {
  if (USE_MOCK) {
    await delay(MOCK_LATENCY_MS)
    return camelizeDeep<RawLogEntry[]>(mockRawLogs)
  }
  try {
    const raw = await http<Raw>(endpoints.rawLogs())
    const list = Array.isArray(raw) ? raw : (raw?.logs || [])
    return camelizeDeep<RawLogEntry[]>(list)
  } catch (err) {
    // 原始日志属于附加能力，后端没实现时不该让整个界面挂掉
    console.warn('[api] /api/logs 不可用，回落到本地 mock 日志：', (err as Error).message)
    return camelizeDeep<RawLogEntry[]>(mockRawLogs)
  }
}

export { MOCK_STORE }
