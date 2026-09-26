import { useCallback } from "react"
import {
  fetchAccount, fetchHealth, fetchLiveFrame, fetchProgress,
  fetchSourceStone, fetchTasks, fetchTrainingMetrics, fetchTrainingRuns,
} from "@/api/endpoints"
import { usePolling } from "@/lib/hooks"
import { SystemStatusCard } from "./dashboard/SystemStatusCard"
import { LiveCard } from "./dashboard/LiveCard"
import { ResourcesCard } from "./dashboard/ResourcesCard"
import { TasksCard } from "./dashboard/TasksCard"
import { TrainingCard } from "./dashboard/TrainingCard"
import { QuickLinksCard } from "./dashboard/QuickLinksCard"

export default function Dashboard() {
  const health = usePolling(fetchHealth, 5000)
  const live = usePolling(fetchLiveFrame, 3000)
  // 资源三个独立接口（设计稿 §3.3），并发轮询
  const sourceStone = usePolling(fetchSourceStone, 10000)
  const account = usePolling(fetchAccount, 10000)
  const progress = usePolling(fetchProgress, 10000)
  const tasks = usePolling(fetchTasks, 10000)
  // 训练：runs 元数据 + 选中 run 的 metrics 时间序列（设计稿 §3.5）
  const trainingRuns = usePolling(fetchTrainingRuns, 20000)
  const firstRunId = trainingRuns.data?.runs?.[0]?.runId ?? null
  const fetchFirstRunMetrics = useCallback(
    () => (firstRunId ? fetchTrainingMetrics(firstRunId) : Promise.resolve(null)),
    [firstRunId],
  )
  const trainingMetrics = usePolling(fetchFirstRunMetrics, 20000)

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <SystemStatusCard data={health.data} />
      <div className="xl:col-span-2">
        <LiveCard data={live.data} />
      </div>
      <ResourcesCard
        sourceStone={sourceStone.data}
        account={account.data}
        progress={progress.data}
      />
      <TasksCard data={tasks.data} />
      <TrainingCard runs={trainingRuns.data} metrics={trainingMetrics.data} />
      <div className="xl:col-span-3">
        <QuickLinksCard />
      </div>
    </div>
  )
}
