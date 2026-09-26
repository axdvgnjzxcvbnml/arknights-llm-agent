// 知识库前端类型 —— 严格对齐后端 HTTP 响应（api/server.py 经 Pydantic by_alias 序列化）。
// 前端不再本地建图/复刻规则；下列类型即各 /api/* 接口的返回形状。

export type NodeKind = 'operator' | 'enemy' | 'stage' | 'skill';
export type DocType = 'operator' | 'enemy' | 'stage' | 'guide';
// fact=PRTS 结构化事实；retrieved=RAG 参考资料（需核实）；inferred=规则推断（非事实）
export type EvidenceLevel = 'fact' | 'retrieved' | 'inferred';
export type Relation = 'HAS_SKILL' | 'CONTAINS_ENEMY' | 'COUNTERS' | 'RECOMMENDS';

// ---------------- GET /api/operator/{name} -> OperatorOut ----------------
export interface SkillLevel {
  level: string;
  desc: string;
  initial: string;
  cost: string;
  duration: string;
}

export interface SkillBrief {
  name: string;
  type: string;
  levels: SkillLevel[];
}

export interface TraitInfo {
  branch: string;
  desc: string;
  branch_info: string;
}

export interface OperatorDetail {
  found: boolean;
  message: string;
  evidence: EvidenceLevel;
  source_url?: string | null;
  name: string;
  display_name: string;
  star_rating?: number | null;
  class: string; // OperatorOut.operator_class 的 by_alias 键
  branch: string;
  position: string;
  tags: string[];
  faction: string;
  deploy_cost: string;
  trait?: TraitInfo | null;
  extra_attrs: Record<string, string>;
  skills: SkillBrief[];
}

// ---------------- GET /api/search -> GuideOut ----------------
// GuideHit 字段是扁平结构（非嵌套 metadata），doc_type 序列化为别名 `type`。
export interface RagHit {
  content: string;
  score: number; // 0~1（真实为 1 - cosine 距离；mock 为本地 bigram 归一化分）
  source: string;
  type: DocType;
  section: string;
  url: string;
  evidence: EvidenceLevel;
}

export interface SearchResponse {
  found: boolean;
  query?: string;
  evidence: 'retrieved';
  embedding_backend?: string;
  note: string;
  hits: RagHit[];
}

// ---------------- GET /api/graph/subgraph/{stage_id} ----------------
export interface GraphNodeApi {
  node_id: string; // operator:名 / enemy:名 / stage:编号 / skill:名:技能
  kind: NodeKind;
  name: string;
  class?: string;
  star?: number | null;
}

export interface SubgraphEdge {
  source: string;
  target: string;
  relation: Relation;
  evidence: EvidenceLevel;
  // CONTAINS_ENEMY(fact)
  count?: string;
  level?: string;
  // RECOMMENDS(inferred)
  support?: number;
  score?: number;
}

export interface SubgraphResponse {
  found: boolean;
  evidence: EvidenceLevel;
  stage_id: string;
  stage_title: string;
  enemy_count: number;
  operator_count: number;
  operators_truncated: boolean;
  operator_cap: number;
  nodes: GraphNodeApi[];
  edges: SubgraphEdge[];
  note: string;
}

// ---------------- GET /api/graph/node/{id} ----------------
export interface NodeNeighbor {
  node_id: string;
  kind: NodeKind;
  name: string;
  relation: Relation;
  direction: 'in' | 'out';
}

export interface NodeDetailResponse {
  found: boolean;
  evidence: EvidenceLevel;
  node_id: string;
  attrs: Record<string, unknown>;
  neighbor_count: number;
  neighbors_shown: number;
  neighbors_truncated: boolean;
  neighbors: NodeNeighbor[];
}

// ---------------- GET /api/recommend/{stage_id} -> RecommendOut ----------------
export interface RecommendedOperator {
  operator: string;
  class: string; // operator_class 的 by_alias 键
  star?: number | null;
  score: number;
  support: number;
  matched_enemies: string[];
  matched_rules: string[];
  evidence: 'inferred';
}

export interface RecommendResponse {
  found: boolean;
  message?: string;
  evidence: 'inferred';
  source_url?: string | null;
  stage_id: string;
  constraints_applied: Record<string, unknown>;
  operators: RecommendedOperator[];
  note: string;
}

// ---------------- mock 选择器目录（真实模式退化为内置 FEATURED）----------------
export interface CatalogEntry {
  name?: string;
  class?: string;
  star?: number | null;
  stage_id?: string;
  title?: string;
}
export interface Catalog {
  operators: CatalogEntry[];
  stages: CatalogEntry[];
}
