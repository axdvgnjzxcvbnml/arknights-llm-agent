// 数据访问层（方案 A：前端只消费后端 API，不在本地建图/复刻克制规则）。
//
// USE_MOCK = true ：读取 public/mock/** 下的"接口夹具"（由 scripts/gen_mock.py 用后端
//                   真实代码生成，形状与 /api/* 完全一致），离线即可联调。
// USE_MOCK = false：调用真实 FastAPI（/api/*）；dev 下由 vite proxy 转发到 :8000。
//
// 两种模式返回的 TS 类型完全一致，页面无需感知差异。
import type {
  Catalog, DocType, NodeDetailResponse, OperatorDetail, RecommendResponse,
  RagHit, SearchResponse, SubgraphResponse,
} from '@/types/kb';

// 默认 mock；联调真实后端时设 VITE_USE_MOCK=false（或直接改这里）
export const USE_MOCK: boolean =
  (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false';

const MOCK_BASE = `${import.meta.env.BASE_URL}mock`;

// 后端目前没有"列出全部干员/关卡"的接口，选择器使用这份精选清单。
// mock 模式会被 public/mock/catalog.json 的标签补全；真实模式直接用下列条目。
export const FEATURED_OPERATORS = ['阿米娅', '能天使', '克洛丝', '梓兰', '翎羽', '安赛尔'];
export const FEATURED_STAGES = [
  { stage_id: '3-8', title: '3-8 黄昏' },
  { stage_id: '1-7', title: '1-7 万岁' },
];

async function fetchJson(url: string): Promise<unknown> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`fetch failed ${r.status}: ${url}`);
  return r.json();
}

// 404 等"实体不存在"统一返回 null（业务未命中，不抛出）
async function fetchOrNull<T>(url: string): Promise<T | null> {
  try {
    return (await fetchJson(url)) as T;
  } catch (e) {
    if (e instanceof Error && /\b404\b/.test(e.message)) return null;
    throw e;
  }
}

const enc = encodeURIComponent;
const nodeFile = (nodeId: string) => nodeId.replace(/:/g, '_');

// ---------------- 干员详情 ----------------
export async function getOperatorDetail(name: string): Promise<OperatorDetail | null> {
  const url = USE_MOCK
    ? `${MOCK_BASE}/operator/${enc(name)}.json`
    : `/api/operator/${enc(name)}`;
  const data = await fetchOrNull<OperatorDetail>(url);
  if (data && data.found === false) return null;
  return data;
}

// ---------------- 图谱节点邻居（干员克制敌人 / 被哪些关卡推荐）----------------
export async function getNodeDetail(nodeId: string): Promise<NodeDetailResponse | null> {
  const url = USE_MOCK
    ? `${MOCK_BASE}/node/${enc(nodeFile(nodeId))}.json`
    : `/api/graph/node/${enc(nodeId)}`;
  const data = await fetchOrNull<NodeDetailResponse>(url);
  if (data && data.found === false) return null;
  return data;
}

// ---------------- 关卡子图 ----------------
export async function getStageSubgraph(stageId: string): Promise<SubgraphResponse | null> {
  const url = USE_MOCK
    ? `${MOCK_BASE}/subgraph/${enc(stageId)}.json`
    : `/api/graph/subgraph/${enc(stageId)}`;
  const data = await fetchOrNull<SubgraphResponse>(url);
  if (data && data.found === false) return null;
  return data;
}

// ---------------- 关卡推荐干员 ----------------
export async function getRecommend(stageId: string): Promise<RecommendResponse | null> {
  const url = USE_MOCK
    ? `${MOCK_BASE}/recommend/${enc(stageId)}.json`
    : `/api/recommend/${enc(stageId)}`;
  const data = await fetchOrNull<RecommendResponse>(url);
  if (data && data.found === false) return null;
  return data;
}

// ---------------- 选择器目录 ----------------
let catalogCache: Catalog | null = null;
export async function loadCatalog(): Promise<Catalog> {
  if (catalogCache) return catalogCache;
  if (!USE_MOCK) {
    catalogCache = {
      operators: FEATURED_OPERATORS.map((name) => ({ name })),
      stages: FEATURED_STAGES.map((s) => ({ ...s })),
    };
    return catalogCache;
  }
  catalogCache = (await fetchJson(`${MOCK_BASE}/catalog.json`)) as Catalog;
  return catalogCache;
}

// ---------------- RAG 检索 ----------------
interface MockCorpus {
  note: string;
  hits: RagHit[];
}
let corpusCache: Promise<MockCorpus> | null = null;
function loadCorpus(): Promise<MockCorpus> {
  if (!corpusCache) {
    corpusCache = fetchJson(`${MOCK_BASE}/search_corpus.json`) as Promise<{
      note: string;
      hits: RagHit[];
    }>;
  }
  return corpusCache;
}

// 简易中文 unigram+bigram 相似度，仅用于 mock 阶段的本地排序演示
function tokenize(s: string): string[] {
  const clean = s.toLowerCase().replace(/[^a-z0-9一-鿿]+/g, ' ');
  const tokens: string[] = [];
  for (const w of clean.split(/\s+/).filter(Boolean)) {
    if (/^[一-鿿]+$/.test(w)) {
      for (const ch of w) tokens.push(ch);
      for (let i = 0; i < w.length - 1; i++) tokens.push(w.slice(i, i + 2));
    } else {
      tokens.push(w);
    }
  }
  return tokens;
}

export async function searchRag(
  query: string,
  k: number,
  docType: DocType | null,
): Promise<SearchResponse> {
  if (!USE_MOCK) {
    const params = new URLSearchParams({ q: query, k: String(k) });
    if (docType) params.set('doc_type', docType); // 对齐后端（不是 type=）
    return (await fetchJson(`/api/search?${params}`)) as SearchResponse;
  }

  const corpus = await loadCorpus();
  const qtokens = tokenize(query);
  const qset = new Set(qtokens);
  const scored = corpus.hits
    .map((h) => {
      if (docType && h.type !== docType) return null;
      const ctokens = tokenize(`${h.content} ${h.section} ${h.source}`);
      if (!ctokens.length || !qtokens.length) return null;
      let hit = 0;
      for (const t of ctokens) if (qset.has(t)) hit++;
      // 0~1 量纲，与真实 score（1 - cosine 距离）一致，前端统一按百分比渲染
      const score = hit / Math.sqrt(qtokens.length * ctokens.length);
      return { ...h, score: Math.round(score * 10000) / 10000 };
    })
    .filter((h): h is RagHit => h != null && h.score > 0);
  scored.sort((a, b) => b.score - a.score);
  return {
    found: true,
    query,
    evidence: 'retrieved',
    embedding_backend: 'mock',
    note: corpus.note,
    hits: scored.slice(0, k),
  };
}

export const TYPE_LABEL: Record<DocType, string> = {
  operator: '干员',
  enemy: '敌人',
  stage: '关卡',
  guide: '攻略',
};
