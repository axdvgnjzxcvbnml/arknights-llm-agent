import { Card } from "@/components/Card"
import { formatDuration } from "@/lib/utils"
import type { TasksResponse, TaskStatus } from "@/types"

const STATUS_STYLE: Record<TaskStatus, string> = {
  running: "bg-emerald-400",
  waiting: "bg-amber-400",
  queued: "bg-slate-400",
  done: "bg-sky-400",
  failed: "bg-rose-400",
}

export function TasksCard({ data }: { data: TasksResponse | null }) {
  const cur = data?.current
  return (
    <Card title="任务队列" extra={<span className="text-xs text-slate-500">/api/tasks（🆕）</span>}>
      {cur ? (
        <div className="mb-3 rounded-md border border-emerald-400/30 bg-emerald-500/5 p-2.5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-100">
              <span className={`h-2 w-2 animate-pulse rounded-full ${STATUS_STYLE[cur.status]}`} />
              {cur.title}
            </span>
            <span className="text-[11px] text-slate-400">{formatDuration(cur.elapsedMs)}</span>
          </div>
          {cur.detail ? <p className="mt-1 text-xs text-slate-400">{cur.detail}</p> : null}
        </div>
      ) : (
        <p className="mb-3 text-xs text-slate-500">当前无运行任务</p>
      )}

      <p className="mb-1.5 text-[11px] uppercase tracking-wide text-slate-500">下一步计划</p>
      <ul className="space-y-1.5">
        {data?.upcoming.map((t) => (
          <li key={t.id} className="flex items-center justify-between gap-2 rounded-md bg-white/5 px-2.5 py-1.5 text-xs">
            <span className="flex items-center gap-2 text-slate-200">
              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_STYLE[t.status]}`} />
              {t.title}
            </span>
            <span className="text-[11px] text-slate-500">{t.status}</span>
          </li>
        ))}
        {!data?.upcoming.length ? <li className="text-xs text-slate-500">队列为空</li> : null}
      </ul>
    </Card>
  )
}
