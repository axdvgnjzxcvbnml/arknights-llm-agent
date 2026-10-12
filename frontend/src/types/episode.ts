// 对局回放（/replay）的 DTO 类型定义。
//
// 命名与来源：
//   - 视图模型（*Dto）字段一律 camelCase：API 层 normalize* 会把后端 snake_case 转过来，
//     组件只消费这里的类型，不直接碰 wire 格式（与 src/types/index.ts 的口径一致）。
//   - 结构对齐后端 pydantic 模型：
//       EpisodeLog / EnvStep        -> env/arknights_env.py
//       RewardBreakdown / RewardItem-> env/reward.py
//       GameState 及其子结构         -> perception/schemas.py
//       AgentDecision / Reasoning /
//       KnowledgeBundle / BridgeState /
//       FastCommand / Reflection    -> agent/output_schema.py
//       Action / ActionPlan / PlanResult -> action/action_space.py
//
// ⚠️ 契约缺口（已在 PR 与 GitHub Issue 记录，勿在前端臆造字段）：
//   #1 steps 里没有结构化 GameState（只有 trace.state_excerpt 文本）
//   #2 对局级没有地图拓扑 map
//   #3 缺 max_steps / step_dt_sec / outcome_label / title
// 因此下面标了 `?` 或 `| null` 的字段，在 VITE_USE_MOCK=false 时确实可能缺失，
// 组件必须走空态分支；mock 数据（scripts/export_mock.py 生成）则是全字段齐全的。

import type { EvidenceLevel } from '@/types/index'

/**
 * 回放侧用到的证据分级。
 * 后端 agent/output_schema.py 的 EvidenceLevel 有 7 档（含 `annotated`），
 * 而 src/types/index.ts 的 EvidenceLevel 用的是 `vlm` 而没有 `annotated`；
 * perception 的 SpawnSource 还会出现 `timer:estimated` / `timer:annotated` / `vlm`。
 * 这里取并集，避免为了迁就某一处而丢掉分级（差异已在 PR 中提请统一）。
 */
export type ReplayEvidenceLevel = EvidenceLevel | 'annotated'

// ---------------------------------------------------------------- 动作空间
export type ActionType = 'deploy' | 'skill' | 'retreat' | 'wait'
export type Direction = 'up' | 'down' | 'left' | 'right'

/** 单个原子动作（action/action_space.py::Action） */
export interface Action {
  action: ActionType
  operatorId?: string | null
  gridPos?: string | null
  direction?: Direction
  skillId?: number | null
  durationMs?: number | null
}

/** 一次决策输出的有序动作序列（ActionPlan） */
export interface ActionPlan {
  actions: Action[]
  reason?: string
}

/** 单个动作的执行结果（ActionResult），ops 为实际下发的 ADB 原语序列 */
export interface ActionResult {
  index: number
  action: string
  success: boolean
  status: string
  error: string
  ops: string[]
}

/** 整段动作序列的执行结果（PlanResult） */
export interface PlanResult {
  total: number
  succeeded: number
  failed: number
  completed: boolean
  results: ActionResult[]
}

// ---------------------------------------------------------------- 感知状态
/** 读数来源（perception.schemas.ReadingSource） */
export type ReadingSource = 'cv' | 'mock' | 'manual'

/** 波次来源（perception.schemas.SpawnSource） */
export type SpawnSource = 'timer:annotated' | 'timer:estimated' | 'cv' | 'vlm' | 'mock'

export type Terrain = 'ground' | 'highland' | 'blocked'

/** 费用读数：state 表示 OCR 读数是否可信 */
export interface CostStatus {
  current: number
  limit: number | null
  confidence: number
  source: ReadingSource
  state: 'ok' | 'uncertain' | 'missing'
}

/** 底部手牌中可部署的干员 */
export interface OperatorCard {
  name: string
  operatorClass: string
  cost: number
  slot: number
  available: boolean
  elite?: number
}

/** 已部署干员 */
export interface DeployedOperator {
  name: string
  cellId: string
  direction: Direction
  hpRatio: number | null
}

/** 技能状态 */
export interface SkillStatus {
  operator: string
  slot: number
  ready: boolean
  active: boolean
  spText: string
  cooldownSec?: number | null
  confidence?: number
  source?: ReadingSource
}

/** 当前场上敌人 */
export interface EnemyPresence {
  name: string
  observedCount: number
  positionHint: string
  source: SpawnSource
}

/** 波次推算：某时刻预计出场的一组敌人 */
export interface SpawnEntry {
  enemy: string
  count: number
  wave: number
  expectedTimeSec: number
  appeared: boolean
  confirmedBy: SpawnSource
}

/** 地图格子（静态拓扑，对局内不变） */
export interface MapCell {
  cellId: string
  col: number
  row: number
  terrain: Terrain
  deployable: boolean
}

/** 地图拓扑（对局级返回一次；每步只给 occupiedCells） */
export interface MapTopology {
  cols: number
  rows: number
  cells: MapCell[]
}

/** VLM 慢通道的局势判断（本身是 inferred，不是事实） */
export interface VlmAnalysis {
  situation: string
  strategicAdvice: string
  confidence: number
  level: 'inferred'
  analyzer: string
  risks?: string[]
}

/** 一步决策前的游戏状态（perception.schemas.GameState 的前端视图） */
export interface StepStateDto {
  stageId: string
  timestamp?: number
  timingSource: 'annotated' | 'estimated' | 'none'
  cost: CostStatus | null
  lifePoints: number | null
  deployUsed: number | null
  deployLimit: number | null
  operatorCards: OperatorCard[]
  deployed: DeployedOperator[]
  skills: SkillStatus[]
  enemiesOnField: EnemyPresence[]
  spawnPlan: SpawnEntry[]
  /** 已占用格子（Issue #1/#2 落地前，API 模式下为空数组） */
  occupiedCells: string[]
  notes: string[]
  vlm: VlmAnalysis | null
  /** 喂给 LLM 的状态原文，可逐字对照 results/agent_decision_log.txt */
  stateText: string
}

// ---------------------------------------------------------------- 可解释性
/** 一条被决策引用的知识来源（KnowledgeCitation） */
export interface KnowledgeCitation {
  source: string
  detail: string
  evidence: ReplayEvidenceLevel
  docType?: string
  url?: string
  score?: number | null
}

/** 一次知识检索的产物（KnowledgeBundle） */
export interface KnowledgeBundleDto {
  query: string
  contextText: string
  citations: KnowledgeCitation[]
}

/** 结构化思考过程（Reasoning） */
export interface ReasoningDto {
  summary: string
  analysis: string[]
  /** 被舍弃的候选动作及原因 */
  consideredActions: string[]
  risks: string[]
}

/** 慢思考输出（AgentDecision 的前端视图） */
export interface DecisionDto {
  decisionId?: string
  stageId?: string
  confidence: number
  thinker: string
  thoughtMs: number
  plan: ActionPlan
}

/** 慢快桥接（BridgeState）。256 维向量不入前端，只留元信息 */
export interface BridgeDto {
  decisionId?: string
  dim: number
  hint: string
  source: 'projected' | 'mock' | string
}

/** 快反应输出（FastCommand） */
export interface CommandDto {
  commandId?: string
  decisionId?: string
  reactor: string
  confidence: number
  reactMs: number
  /** 被快通道判定当前不可执行的动作及原因 */
  dropped: string[]
  note: string
  plan?: ActionPlan
}

/** 自我反思（Reflection） */
export interface ReflectionDto {
  decisionId?: string
  verdict: 'good' | 'risky' | 'bad'
  issues: string[]
  adjustment: string
  confidence: number
}

/** 证据引用（EnvStep.evidence，后端已改为 {level, source} 对象） */
export interface EvidenceRef {
  level: string
  source: string
}

// ---------------------------------------------------------------- 奖励
/** 单条奖励项（RewardItem） */
export interface RewardItemDto {
  name: string
  delta: number
  why: string
}

/** 一局奖励结算（RewardBreakdown） */
export interface RewardBreakdownDto {
  outcome?: string
  total: number
  winBonus: number
  leakPenalty: number
  overcostPenalty: number
  leaked: number
  overcostSec: number
  lifeStart: number | null
  lifeEnd: number | null
  summaryLine: string
  items: RewardItemDto[]
}

/** 单步奖励 */
export interface StepRewardDto {
  stepReward: number
  items: RewardItemDto[]
}

// ---------------------------------------------------------------- 对局
export type Outcome = 'win' | 'defeat' | 'timeout' | 'aborted'

/** 对局级聚合统计（后端未提供时由前端从 steps 兜底计算，见 Issue #3） */
export interface EpisodeTotals {
  actionsTotal: number
  actionsSucceeded: number
  actionsFailed: number
  avgConfidence: number
  latencySumMs: Record<string, number>
}

/** GET /api/episodes 列表项 */
export interface EpisodeSummary {
  id: string
  title?: string
  stageId: string
  backend: string
  outcome: Outcome | string
  outcomeLabel?: string
  stepCount: number
  durationSec: number
  gameTimeSec?: number
  totalReward?: number | null
  generatedAt?: string
}

/** GET /api/episodes 响应 */
export interface EpisodeIndex {
  schemaVersion?: number
  generatedAt?: string
  note?: string
  found?: boolean
  count?: number
  episodes: EpisodeSummary[]
}

/** GET /api/episode/{id} 归一化后的对局报告 */
export interface EpisodeDto extends EpisodeSummary {
  reward: RewardBreakdownDto
  totals: EpisodeTotals
  map: MapTopology
  /** 步数上限（Issue #3：后端暂未提供） */
  maxSteps?: number
  /** 每步代表的对局秒数（Issue #3：后端暂未提供） */
  stepDtSec?: number
  source?: string
}

/** GET /api/episode/{id}/steps 的单步（归一化后） */
export interface StepDto {
  /** 数组下标，从 0 开始；与 step（后端步号，从 1 开始）区分 */
  index: number
  step: number
  elapsedSec: number
  state: StepStateDto
  knowledge: KnowledgeBundleDto
  reasoning: ReasoningDto
  decision: DecisionDto
  bridge: BridgeDto | null
  command: CommandDto | null
  execute: PlanResult | null
  reflection: ReflectionDto | null
  /** 执行后读数 */
  after: { cost: number | null; life: number | null }
  reward: StepRewardDto
  evidence: EvidenceRef[]
  latencyMs: Record<string, number>
}

/** 回放页实际消费的一局完整数据 */
export interface EpisodeFull {
  episode: EpisodeDto
  steps: StepDto[]
}

/** 原始文本日志（results/*.txt 同源） */
export interface RawLogEntry {
  id: string
  title: string
  path: string
  generatedBy: string
  text: string
}

/** mock 文档（web/scripts/export_mock.py 产物）的形状 */
export interface MockEpisodeDoc {
  schemaVersion?: number
  episode: unknown
  steps?: unknown[]
}
