import { Card } from "@/components/Card"
import { EvidenceBadge } from "@/components/EvidenceBadge"
import type { HealthResponse } from "@/types"

export function SystemStatusCard({ data }: { data: HealthResponse | null }) {
  const modules = data ? Object.entries(data.modules) : []
  const vram = data?.vram
  return (
    <Card
      title="系统状态"
      extra={<span className="text-xs text-slate-500">/api/health（扩展字段）</span>}
    >
      <ul className="space-y-1.5">
        {modules.map(([name, m]) => (
          <li key={name} className="flex items-center justify-between gap-2 text-xs">
            <span className="flex items-center gap-2">
              <span
                className={
                  m.online
                    ? "h-2 w-2 rounded-full bg-emerald-400"
                    : "h-2 w-2 rounded-full bg-rose-400"
                }
              />
              <span className="text-slate-200">{name}</span>
            </span>
            <span className="flex items-center gap-2">
              <span className="text-slate-400">
                {m.latencyMsP50 === null ? "延迟 —" : `P50 ${m.latencyMsP50}ms`}
              </span>
              <EvidenceBadge level={m.evidence} source="" />
            </span>
          </li>
        ))}
        {!data ? <li className="text-xs text-slate-500">加载中…</li> : null}
      </ul>
      <div className="mt-3 border-t border-[hsl(var(--border))] pt-2 text-xs text-slate-400">
        显存：
        {vram && vram.usedMb !== null && vram.totalMb !== null
          ? `${(vram.usedMb / 1024).toFixed(1)} / ${(vram.totalMb / 1024).toFixed(1)} GB` +
            (vram.util !== null ? `（利用率 ${(vram.util * 100).toFixed(0)}%）` : "")
          : "N/A（无 GPU / mock）"}
      </div>
    </Card>
  )
}
