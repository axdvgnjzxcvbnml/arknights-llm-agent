import { fetchJson } from "./client"
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
