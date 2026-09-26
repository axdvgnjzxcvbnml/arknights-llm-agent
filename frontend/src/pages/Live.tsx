import { fetchLiveFrame } from "@/api/endpoints"
import { Card } from "@/components/Card"
import { EvidenceBadge, EvidenceList } from "@/components/EvidenceBadge"
import { usePolling } from "@/lib/hooks"
import { asPercent, formatDateTime, formatDuration } from "@/lib/utils"

export default function Live() {
  const { data, error } = usePolling(fetchLiveFrame, 3000)

  if (error) return <Card title="实时对局"><p className="text-sm text-rose-300">连接失败：{error}</p></Card>

  return (
    <div className="space-y-4">
      <Card title="实时对局（/live · WS 待接入，当前轮询快照）">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="relative aspect-video w-full overflow-hidden rounded-md border border-[hsl(var(--border))] bg-black/40">
            {data?.screenshotDataUrl ? (
              <img src={data.screenshotDataUrl} alt="游戏画面（本地流）" className="h-full w-full object-contain" />
            ) : (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <p className="text-sm text-slate-400">MOCK：无真实游戏画面</p>
                <p className="mt-1 text-xs text-slate-600">真机帧经 /ws/live 推送，仅本地流转</p>
              </div>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <p className="text-slate-400">
              对局 {data?.episodeId ?? "…"} · 费用 <span className="text-base text-slate-100">{data?.state.cost ?? "—"}</span>
              <span className="ml-2 text-slate-500">{formatDateTime(data?.ts)}</span>
            </p>
            <p className="text-slate-400">可部署格子：{data?.state.deployableGrids.join("、")}</p>
            <div>
              <p className="text-slate-400">敌人</p>
              {data?.state.enemies.map((e) => (
                <p key={e.name} className="flex items-center gap-2 py-0.5">
                  {e.name} ×{e.count}
                  <EvidenceBadge level={e.status === "cv" ? "cv" : "estimated"} source={e.status === "cv" ? "已确认" : "时间轴"} />
                </p>
              ))}
            </div>
            {data?.vlm ? (
              <div className="rounded-md border border-violet-400/30 bg-violet-500/5 p-2">
                <p className="text-violet-300">{data.vlm.situation}</p>
                <p className="mt-1 text-slate-400">建议：{data.vlm.strategicAdvice}</p>
                <EvidenceList items={data.vlm.evidence} className="mt-1" />
              </div>
            ) : null}
          </div>
        </div>
      </Card>

      <Card title="决策流时间线">
        <ol className="space-y-2">
          {data?.decisionFlow.map((d) => (
            <li key={d.step} className="rounded-md bg-white/5 p-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-200">第 {d.step} 步</span>
                <span className="text-slate-400">
                  置信 {asPercent(d.confidence)} · {formatDuration(d.latencyMs)}
                </span>
              </div>
              <p className="mt-1 text-slate-300">{d.reasoning}</p>
              <p className="mt-1 font-mono text-[11px] text-[hsl(var(--primary))]">{d.action}</p>
              <EvidenceList items={d.knowledgeUsed} className="mt-1.5" />
            </li>
          ))}
          {!data ? <p className="text-xs text-slate-500">加载中…</p> : null}
        </ol>
      </Card>
    </div>
  )
}
