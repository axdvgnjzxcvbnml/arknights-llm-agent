// 全前端统一类型定义。
// 后端 wire 格式为 snake_case（见 docs/api.md / docs/dashboard_design.md），
// API 层用 deepCamelize 转成这里的 camelCase 后再给组件；组件不直接消费 snake_case。

/** 证据分级（7 档）。retrieved/inferred/estimated 用虚线边框，表示非确定事实。 */
export type EvidenceLevel =
  | "fact"        // 确定事实（账号/关卡实测、游戏规则）
  | "retrieved"   // 检索到的外部资料（RAG/强度榜观点），非事实判定
  | "inferred"    // 规则/模型推断
  | "estimated"   // 估算值（如均匀出怪时间轴、短期窗口）
  | "cv"          // CV 快通道确认
  | "vlm"         // VLM 慢通道观点
  | "mock";       // mock 数据

export interface Evidence {
  level: EvidenceLevel;
  source: string;
}

// ---------------- /api/health（扩展后，🟡=待后端补字段） ----------------
export interface ModuleHealth {
  online: boolean;
  evidence: EvidenceLevel;
  latencyMsP50: number | null; // 无采样时为 null，不画假数字
}

export interface VramInfo {
  usedMb: number | null;
  totalMb: number | null;
  util: number | null; // 0..1，无 GPU（mock/CPU）时全 null
}

export interface HealthResponse {
  env: "mock" | "v100" | "device" | string;
  serverVersion: string;
  ts: string;
  modules: Record<string, ModuleHealth>;
  vram: VramInfo;
}

// ---------------- /ws/live（🆕，先用 mock） ----------------
export interface AvailableOperator {
  name: string;
  profession: string;
  cost: number;
}

export interface EnemySpawn {
  name: string;
  count: number;
  status: "estimated" | "cv";
}

export interface SkillCooldown {
  operator: string;
  ready: boolean;
  remainingMs: number | null;
}

export interface VlmView {
  situation: string;
  strategicAdvice: string;
  confidence: number;
  evidence: Evidence[];
}

export interface KnowledgeRef {
  level: EvidenceLevel;
  source: string;
  snippet?: string;
}

export interface DecisionStep {
  step: number;
  reasoning: string;
  action: string;
  confidence: number;
  knowledgeUsed: KnowledgeRef[];
  latencyMs: number;
}

export interface GameStateView {
  cost: number;
  availableOperators: AvailableOperator[];
  skillCooldowns: SkillCooldown[];
  enemies: EnemySpawn[];
  deployableGrids: string[];
}

export interface LiveFrame {
  connected: boolean;
  episodeId: string | null;
  screenshotDataUrl: string | null; // 仅本地内存/网络流转，不入 git；mock 为占位图
  state: GameStateView;
  vlm: VlmView | null;
  decisionFlow: DecisionStep[];
  latencyMs: Record<string, number>;
  ts: string;
}

// ---------------- /api/resources/*（🆕，先用 mock） ----------------
export interface StoneTier {
  normalStone: number;
  raidStone: number;
}

export interface SourceStone {
  currentStone: number;
  totalRemaining: number;
  promptDecisionStone: number; // 仅 立即+短期，喂抽卡决策
  longTermStone: number;       // 长期档，只展示不进决策
  shortTermWindow: number;
  tiers: {
    immediate: StoneTier;
    shortTerm: StoneTier;
    longTerm: StoneTier;
  };
}

export interface AccountResources {
  orundum: number | null;
  originite: number | null;
  lmd: number | null;
  operatorCount: number | null;
  evidence: EvidenceLevel;
}

export interface StageProgress {
  cleared: number;
  total: number;
  currentChapter: string;
  evidence: EvidenceLevel;
}

export interface ResourcesResponse {
  sourceStone: SourceStone;
  account: AccountResources;
  progress: StageProgress;
}

// ---------------- /api/tasks（🆕，先用 mock） ----------------
export type TaskStatus = "running" | "waiting" | "queued" | "done" | "failed";

export interface TaskItem {
  id: string;
  title: string;
  status: TaskStatus;
  detail: string;
  elapsedMs: number | null;
}

export interface TasksResponse {
  current: TaskItem | null;
  upcoming: TaskItem[];
}

// ---------------- /api/training/*（🆕 V100，mock 为示例数据） ----------------
export interface TrainMetricPoint {
  step: number;
  trainLoss: number;
  evalLoss: number | null;
  lr: number;
}

export interface EvalMetrics {
  formatCompliance: number | null;
  accuracy: number | null;
}

export interface TrainingRun {
  runId: string;
  baseModel: string;
  lora: { rank: number; alpha: number; dropout: number };
  status: TaskStatus;
  currentStep: number;
  totalSteps: number;
  example: boolean; // true=mock 示例曲线，非真实训练
  metrics: TrainMetricPoint[];
  eval: EvalMetrics;
}

export interface TrainingResponse {
  connected: boolean; // V100 是否接入
  runs: TrainingRun[];
}
