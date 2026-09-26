import { fetchJson } from "./client"
import type {
  HealthResponse,
  LiveFrame,
  ResourcesResponse,
  TasksResponse,
  TrainingResponse,
} from "@/types"

// 实时对局：真实实现走 WS /ws/live（后端🆕）；当前 HTTP 拉一帧快照即可（mock）。
// 合并 Qwen web/ 时，这里替换为 WebSocket 订阅，页面侧只换 hook 不换类型。
export function fetchHealth(): Promise<HealthResponse> {
  return fetchJson("health", "/api/health")
}

export function fetchLiveFrame(): Promise<LiveFrame> {
  return fetchJson("live", "/api/live/snapshot")
}

export function fetchResources(): Promise<ResourcesResponse> {
  return fetchJson("resources", "/api/resources/account")
}

export function fetchTasks(): Promise<TasksResponse> {
  return fetchJson("tasks", "/api/tasks")
}

export function fetchTraining(): Promise<TrainingResponse> {
  return fetchJson("training", "/api/training/runs")
}
