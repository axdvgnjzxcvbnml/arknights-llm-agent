import { fetchJson, fetchJsonOrNull, USE_MOCK } from "./client"
import type {
  AccountResources,
  HealthResponse,
  LiveFrame,
  SourceStone,
  StageProgress,
  TaskItem,
  TrainingMetricsResponse,
  TrainingRunsResponse,
} from "@/types"
import type {
  Catalog,
  DocType,
  NodeDetailResponse,
  OperatorDetail,
  RagHit,
  RecommendResponse,
  SearchResponse,
  SubgraphResponse,
} from "@/types/kb"

// ---------------- 系统状态 ----------------
// 设计稿 §3.6：扩展 /api/health 返回 modules + vram。
export function fetchHealth(): Promise<HealthResponse> {
  return fetchJson("health", "/api/health")
}

// ---------------- 实时对局 ----------------
// 设计稿 §3.2：HTTP 初始快照 /api/live/snapshot + WS /ws/live 增量推送。
// 当前 usePolling 走 HTTP 快照作为 WS 未接通时的降级；WS 接入后替换 hook 层。
export function fetchLiveFrame(): Promise<LiveFrame> {
  return fetchJson("live", "/api/live/snapshot")
}

// ---------------- 资源（设计稿 §3.3，三个独立接口） ----------------
export function fetchSourceStone(): Promise<SourceStone> {
  return fetchJson("source-stone", "/api/resources/source-stone")
}

export function fetchAccount(): Promise<AccountResources> {
  return fetchJson("account", "/api/resources/account")
}

export function fetchProgress(): Promise<StageProgress> {
  return fetchJson("progress", "/api/resources/progress")
}

// ---------------- 任务队列（设计稿 §3.4） ----------------
export interface TasksResponse {
  current: TaskItem | null;
  upcoming: TaskItem[];
}
export function fetchTasks(): Promise<TasksResponse> {
  return fetchJson("tasks", "/api/tasks")
}

// ---------------- 训练（设计稿 §3.5，runs 元数据 + metrics 时间序列分离） ----------------
export function fetchTrainingRuns(): Promise<TrainingRunsResponse> {
  return fetchJson("training-runs", "/api/training/runs")
}

export function fetchTrainingMetrics(runId: string): Promise<TrainingMetricsResponse> {
  return fetchJson("training-metrics", `/api/training/metrics?run=${encodeURIComponent(runId)}`)
}

// ============================================================================
// 知识库 API（从 web-kb 移植，方案 A：前端只消费后端 API）
// ============================================================================

const enc = encodeURIComponent
const nodeFile = (nodeId: string) => nodeId.replace(/:/g, "_")

// 干员/关卡精选清单（真实模式下后端无列表接口时用）
export const FEATURED_OPERATORS = ["阿米娅", "能天使", "克洛丝", "梓兰", "翎羽", "安赛尔"]
export const FEATURED_STAGES = [
  { stageId: "3-8", title: "3-8 黄昏" },
  { stageId: "1-7", title: "1-7 万岁" },
]

export const TYPE_LABEL: Record<DocType, string> = {
  operator: "干员",
  enemy: "敌人",
  stage: "关卡",
  guide: "攻略",
}

/** 干员详情 → /api/operator/{name} */
export async function getOperatorDetail(name: string): Promise<OperatorDetail | null> {
  const data = await fetchJsonOrNull<OperatorDetail>(`operator/${enc(name)}`, `/api/operator/${enc(name)}`)
  if (data && (data as { found?: boolean }).found === false) return null
  return data
}

/** 图谱节点邻居 → /api/graph/node/{nodeId} */
export async function getNodeDetail(nodeId: string): Promise<NodeDetailResponse | null> {
  const data = await fetchJsonOrNull<NodeDetailResponse>(
    `node/${enc(nodeFile(nodeId))}`,
    `/api/graph/node/${enc(nodeId)}`,
  )
  if (data && (data as { found?: boolean }).found === false) return null
  return data
}

/** 关卡子图 → /api/graph/subgraph/{stageId} */
export async function getStageSubgraph(stageId: string): Promise<SubgraphResponse | null> {
  const data = await fetchJsonOrNull<SubgraphResponse>(`subgraph/${enc(stageId)}`, `/api/graph/subgraph/${enc(stageId)}`)
  if (data && (data as { found?: boolean }).found === false) return null
  return data
}

/** 关卡推荐干员 → /api/recommend/{stageId} */
export async function getRecommend(stageId: string): Promise<RecommendResponse | null> {
  const data = await fetchJsonOrNull<RecommendResponse>(`recommend/${enc(stageId)}`, `/api/recommend/${enc(stageId)}`)
  if (data && (data as { found?: boolean }).found === false) return null
  return data
}

/** 选择器目录 → mock/catalog.json 或 FEATURED 清单 */
let catalogCache: Catalog | null = null
export async function loadCatalog(): Promise<Catalog> {
  if (catalogCache) return catalogCache
  if (!USE_MOCK) {
    catalogCache = {
      operators: FEATURED_OPERATORS.map((name) => ({ name })),
      stages: FEATURED_STAGES.map((s) => ({ ...s })),
    }
    return catalogCache
  }
  catalogCache = await fetchJson<Catalog>("catalog", "/api/graph/overview")
  return catalogCache
}

// ---- RAG 检索（mock 模式下本地排序，真实模式调 /api/search）----
interface MockCorpus { note: string; hits: RagHit[] }
let corpusCache: Promise<MockCorpus> | null = null

function tokenize(s: string): string[] {
  const clean = s.toLowerCase().replace(/[^a-z0-9一-鿿]+/g, " ")
  const tokens: string[] = []
  for (const w of clean.split(/\s+/).filter(Boolean)) {
    if (/^[一-鿿]+$/.test(w)) {
      for (const ch of w) tokens.push(ch)
      for (let i = 0; i < w.length - 1; i++) tokens.push(w.slice(i, i + 2))
    } else {
      tokens.push(w)
    }
  }
  return tokens
}

export async function searchRag(query: string, k: number, docType: DocType | null): Promise<SearchResponse> {
  if (!USE_MOCK) {
    const params = new URLSearchParams({ q: query, k: String(k) })
    if (docType) params.set("doc_type", docType)
    return await fetchJson<SearchResponse>("search", `/api/search?${params}`)
  }
  // mock 本地排序
  if (!corpusCache) corpusCache = fetchJson<{ note: string; hits: RagHit[] }>("search_corpus", "/api/search")
  const corpus = await corpusCache
  const qtokens = tokenize(query)
  const qset = new Set(qtokens)
  const scored = corpus.hits
    .map((h) => {
      if (docType && h.type !== docType) return null
      const ctokens = tokenize(`${h.content} ${h.section} ${h.source}`)
      if (!ctokens.length || !qtokens.length) return null
      let hit = 0
      for (const t of ctokens) if (qset.has(t)) hit++
      const score = hit / Math.sqrt(qtokens.length * ctokens.length)
      return { ...h, score: Math.round(score * 10000) / 10000 }
    })
    .filter((h): h is RagHit => h != null && h.score > 0)
  scored.sort((a, b) => b.score - a.score)
  return {
    found: true,
    query,
    evidence: "retrieved",
    embeddingBackend: "mock",
    note: corpus.note,
    hits: scored.slice(0, k),
  }
}
