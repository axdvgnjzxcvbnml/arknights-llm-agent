import { Link } from "react-router"
import { Card } from "@/components/Card"
import { EvidenceBadge, EvidenceList } from "@/components/EvidenceBadge"
import { asPercent, formatDuration } from "@/lib/utils"
import type { LiveFrame } from "@/types"

function ScreenshotBox({ data }: { data: LiveFrame | null }) {
  const url = data?.screenshotDataUrl
  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-md border border-[hsl(var(--border))] bg-black/40">
      {url ? (
        <img src={url} alt="游戏画面（本地流）" className="h-full w-full object-contain" />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
          <p className="text-xs text-slate-400">MOCK：无真实游戏画面</p>
          <p className="text-[11px] text-slate-600">真机帧仅本地内存/网络流转，不入 git</p>
        </div>
      )}
    </div>
  )
}

export function LiveCard({ data }: { data: LiveFrame | null }) {
  const s = data?.state
  const last = data?.decisionFlow?.[data.decisionFlow.length - 1]
  return (
    <Card
      title="实时对局"
      extra={
        <Link to="/live" className="text-xs text-[hsl(var(--primary))] hover:underline">
          进入 /live
        </Link>
      }
      bodyClassName="space-y-3"
    >
      <ScreenshotBox data={data} />

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="mb-1 text-slate-400">
            费用 <span className="text-base font-semibold text-slate-100">{s?.cost ?? "—"}</span>
          </p>
          <p className="text-slate-400">可部署干员</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {s?.availableOperators.map((o) => (
              <span key={o.name} className="rounded-sm bg-white/5 px-1.5 py-0.5 text-slate-200">
                {o.name}({o.cost}费)
              </span>
            ))}
          </div>
        </div>
        <div>
          <p className="text-slate-400">敌人波次</p>
          <ul className="mt-1 space-y-1">
            {s?.enemies.map((e) => (
              <li key={e.name} className="flex items-center gap-1.5">
                <span className="text-slate-200">
                  {e.name} ×{e.count}
                </span>
                <EvidenceBadge
                  level={e.status === "cv" ? "cv" : "estimated"}
                  source={e.status === "cv" ? "已确认" : "时间轴"}
                />
              </li>
            ))}
          </ul>
        </div>
      </div>

      {data?.vlm ? (
        <div className="rounded-md border border-violet-400/30 bg-violet-500/5 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-medium text-violet-300">VLM 慢通道（2s）</span>
            <span className="text-slate-400">置信 {asPercent(data.vlm.confidence)}</span>
          </div>
          <p className="text-slate-300">{data.vlm.situation}</p>
          <p className="mt-1 text-slate-400">建议：{data.vlm.strategicAdvice}</p>
        </div>
      ) : null}

      {last ? (
        <div className="rounded-md bg-white/5 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-slate-400">
              最新决策 · 第 {last.step} 步 · {formatDuration(last.latencyMs)}
            </span>
            <span className="text-slate-300">置信 {asPercent(last.confidence)}</span>
          </div>
          <p className="text-slate-200">{last.reasoning}</p>
          <p className="mt-1 font-mono text-[11px] text-[hsl(var(--primary))]">{last.action}</p>
          <EvidenceList items={last.knowledgeUsed} className="mt-1.5" />
        </div>
      ) : (
        <p className="text-xs text-slate-500">加载中…</p>
      )}
    </Card>
  )
}
