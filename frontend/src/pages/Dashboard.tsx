import {
  fetchHealth, fetchLiveFrame, fetchResources, fetchTasks, fetchTraining,
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
  const resources = usePolling(fetchResources, 10000)
  const tasks = usePolling(fetchTasks, 10000)
  const training = usePolling(fetchTraining, 20000)

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <SystemStatusCard data={health.data} />
      <div className="xl:col-span-2">
        <LiveCard data={live.data} />
      </div>
      <ResourcesCard data={resources.data} />
      <TasksCard data={tasks.data} />
      <TrainingCard data={training.data} />
      <div className="xl:col-span-3">
        <QuickLinksCard />
      </div>
    </div>
  )
}
