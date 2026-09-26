import { fetchAccount, fetchProgress, fetchSourceStone } from "@/api/endpoints"
import { Card, EmptyState } from "@/components/Card"
import { EvidenceBadge } from "@/components/EvidenceBadge"
import { usePolling } from "@/lib/hooks"
import type { StoneTier } from "@/types"

function TierTable({ tiers }: { tiers: { immediate: StoneTier; shortTerm: StoneTier; longTerm: StoneTier } }) {
  const rows = [
    { name: "① 立即可拿", key: "immediate" as const, tone: "text-emerald-300", note: "已解锁未通关/已解锁突袭" },
    { name: "② 短期可拿", key: "shortTerm" as const, tone: "text-amber-300", note: "约1-2天连续关卡（估算）" },
    { name: "③ 长期可拿", key: "longTerm" as const, tone: "text-slate-400", note: "高难/未解锁突袭，仅规划" },
  ]
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-slate-500">
          <th className="pb-1 font-normal">档位</th>
          <th className="pb-1 font-normal">普通首通</th>
          <th className="pb-1 font-normal">突袭首通</th>
          <th className="pb-1 font-normal">合计</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const t = tiers[r.key]
          return (
            <tr key={r.key} className="border-t border-[hsl(var(--border))]">
              <td className={`py-1.5 ${r.tone}`}>
                {r.name}
                <span className="ml-1 text-[11px] text-slate-500">{r.note}</span>
              </td>
              <td className="py-1.5 font-mono">{t.normalStone}</td>
              <td className="py-1.5 font-mono">{t.raidStone}</td>
              <td className="py-1.5 font-mono text-slate-100">{t.normalStone + t.raidStone}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function Resources() {
  const sourceStone = usePolling(fetchSourceStone, 10000)
  const account = usePolling(fetchAccount, 10000)
  const progress = usePolling(fetchProgress, 10000)
  const ss = sourceStone.data
  const acc = account.data
  const prog = progress.data
  if (!ss && !acc && !prog) return <Card title="资源管理"><EmptyState text="加载中…" /></Card>

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card title="至纯源石 · 首通获取三档" extra={<EvidenceBadge level="inferred" source="规则估算" />}>
        {ss ? <TierTable tiers={ss.tiers} /> : <EmptyState text="加载中…" />}
        {ss ? (
          <div className="mt-3 space-y-1 rounded-md border border-amber-400/30 bg-amber-500/5 p-2 text-xs text-amber-200">
            <p>抽卡决策可用（①+②）：<span className="font-mono text-base">{ss.promptDecisionStone}</span> 源石</p>
            <p className="text-slate-400">③ 长期 {ss.longTermStone} 源石只用于总资源规划，不进入抽卡决策 Prompt。</p>
            <p className="text-slate-400">剩余总量 {ss.totalRemaining}；当前持有 {ss.currentStone}（口径见 source_stone_tracker）。</p>
          </div>
        ) : null}
      </Card>

      <div className="space-y-4">
        <Card title="账号资源" extra={acc ? <EvidenceBadge level={acc.evidence} source="gacha/shop 解析" /> : undefined}>
          {acc ? (
            <dl className="grid grid-cols-2 gap-2 text-xs">
              {[
                ["合成玉", acc.orundum], ["至纯源石", acc.originite],
                ["龙门币", acc.lmd], ["干员数", acc.operatorCount],
              ].map(([k, v]) => (
                <div key={k} className="rounded-md bg-white/5 px-2 py-1.5">
                  <dt className="text-slate-400">{k}</dt>
                  <dd className="font-mono text-sm text-slate-100">{v ?? "—"}</dd>
                </div>
              ))}
            </dl>
          ) : <EmptyState text="加载中…" />}
        </Card>
        <Card title="主线关卡进度" extra={prog ? <EvidenceBadge level={prog.evidence} source="结算+台账" /> : undefined}>
          {prog ? (
            <>
              <p className="font-mono text-sm">{prog.cleared} / {prog.total}</p>
              <p className="mt-1 text-xs text-slate-400">当前：{prog.currentChapter}</p>
            </>
          ) : <EmptyState text="加载中…" />}
        </Card>
      </div>
    </div>
  )
}
