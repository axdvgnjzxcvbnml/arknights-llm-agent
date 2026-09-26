import { Link } from "react-router"
import { Card } from "@/components/Card"
import { EvidenceBadge } from "@/components/EvidenceBadge"
import type { ResourcesResponse, StoneTier } from "@/types"

function StoneTierRow({ label, tier, note }: { label: string; tier: StoneTier; note?: string }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-300">
        {label}
        {note ? <span className="ml-1 text-slate-500">{note}</span> : null}
      </span>
      <span className="font-mono text-slate-100">
        {tier.normalStone + tier.raidStone}
        <span className="ml-1 text-[11px] text-slate-500">
          (普{tier.normalStone}/突{tier.raidStone})
        </span>
      </span>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-white/5 px-2 py-1.5">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="font-mono text-sm text-slate-100">{value}</p>
    </div>
  )
}

export function ResourcesCard({ data }: { data: ResourcesResponse | null }) {
  const ss = data?.sourceStone
  const acc = data?.account
  const prog = data?.progress
  const pct = prog && prog.total ? Math.round((prog.cleared / prog.total) * 100) : 0

  return (
    <Card
      title="资源仪表盘"
      extra={<Link to="/resources" className="text-xs text-[hsl(var(--primary))] hover:underline">详情</Link>}
      bodyClassName="space-y-3"
    >
      {ss ? (
        <div className="space-y-1.5 rounded-md border border-[hsl(var(--border))] p-2">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-medium text-slate-200">至纯源石 · 首通剩余三档</span>
            <span className="text-[11px] text-slate-500">当前持有 {ss.currentStone}</span>
          </div>
          <StoneTierRow label="① 立即可拿" tier={ss.tiers.immediate} />
          <StoneTierRow label={`② 短期可拿(${ss.shortTermWindow}关≈1-2天)`} tier={ss.tiers.shortTerm} />
          <StoneTierRow label="③ 长期（不进抽卡决策）" tier={ss.tiers.longTerm} />
          <p className="pt-1 text-[11px] text-amber-300/90">
            抽卡决策只看前两档：共 {ss.promptDecisionStone} 源石；长期 {ss.longTermStone} 仅规划用。
          </p>
        </div>
      ) : (
        <p className="text-xs text-slate-500">加载中…</p>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Metric label="合成玉" value={acc?.orundum ?? "—"} />
        <Metric label="龙门币" value={acc?.lmd ?? "—"} />
        <Metric label="干员数" value={acc?.operatorCount ?? "—"} />
        <Metric label="主线进度" value={prog ? `${prog.cleared}/${prog.total}` : "—"} />
      </div>
      {acc ? <EvidenceBadge level={acc.evidence} source="账号识别" /> : null}

      {prog ? (
        <div>
          <div className="mb-1 flex justify-between text-[11px] text-slate-400">
            <span>{prog.currentChapter}</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-[hsl(var(--primary))]" style={{ width: `${pct}%` }} />
          </div>
        </div>
      ) : null}
    </Card>
  )
}
