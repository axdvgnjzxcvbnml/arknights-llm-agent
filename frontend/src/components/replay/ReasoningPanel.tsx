// @ts-nocheck
import React from 'react'
import { Card, Empty, List } from '@/components/replay/ui'
import EvidenceBadge from './EvidenceBadge.jsx'
import { fmtMs, fmtPct } from '@/lib/utils'

/**
 * 决策理由（可解释性核心）：一句话结论 + 逐条依据 + 候选取舍 + 风险。
 * 对应 AgentDecision.reasoning，是 results/agent_decision_log.txt 里
 * "慢思考 reasoning" 那一段的可视化。
 */
export default function ReasoningPanel({ step }) {
  const r = step.reasoning || {}
  const d = step.decision || {}
  const conf = Number(d.confidence ?? 0)
  const confColor = conf >= 0.7 ? '#34d399' : conf >= 0.45 ? '#fbbf24' : '#fb7185'

  return (
    <Card
      title="决策理由 · 慢思考"
      extra={
        <div className="flex items-center gap-2">
          <span className="chip border-ink-600 bg-ink-800 font-mono text-slate-400">{d.thinker || 'mock'}</span>
          <span className="chip border-ink-600 bg-ink-800 font-mono text-slate-400" title="慢思考耗时">
            {fmtMs(d.thoughtMs, 2)}
          </span>
        </div>
      }
    >
      <div className="rounded-md border border-cyan-400/35 bg-cyan-400/8 px-3 py-2">
        <div className="kv-label mb-0.5">结论 summary</div>
        <div className="text-[15px] font-semibold leading-snug text-cyan-100">{r.summary || '—'}</div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div>
          <div className="card-title mb-1">逐条依据 analysis · {r.analysis?.length || 0}</div>
          <List items={r.analysis || []} ordered />
        </div>
        <div className="space-y-3">
          <div>
            <div className="card-title mb-1">候选与取舍 considered_actions · {r.consideredActions?.length || 0}</div>
            {r.consideredActions?.length ? (
              <ul className="space-y-1">
                {r.consideredActions.map((c, i) => (
                  <li key={i} className="flex gap-1.5 text-[12px] leading-relaxed text-slate-400">
                    <span className="mt-[1px] shrink-0 text-slate-600">✕</span>
                    <span className="min-w-0 flex-1">{c}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>本步无被舍弃的候选动作</Empty>
            )}
          </div>
          <div>
            <div className="card-title mb-1">风险 risks · {r.risks?.length || 0}</div>
            {r.risks?.length ? (
              <ul className="space-y-1">
                {r.risks.map((k, i) => (
                  <li key={i} className="rounded border border-amber-400/30 bg-amber-400/5 px-2 py-1 text-[12px] leading-snug text-amber-200/90">
                    ⚠ {k}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>未识别到风险</Empty>
            )}
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-ink-700/70 pt-2">
        <div className="flex items-center gap-2">
          <span className="kv-label">置信度</span>
          <span className="font-mono text-sm font-semibold" style={{ color: confColor }}>
            {conf.toFixed(2)}
          </span>
          <span className="text-[11px] text-slate-500">{fmtPct(conf)}</span>
          <span className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-700">
            <span className="block h-full rounded-full" style={{ width: `${conf * 100}%`, backgroundColor: confColor }} />
          </span>
        </div>
        {d.decisionId ? <span className="font-mono text-[10px] text-slate-600">{d.decisionId}</span> : null}
        {step.evidence?.length ? (
          <span className="ml-auto flex flex-wrap items-center gap-1">
            <span className="kv-label">本步证据</span>
            {step.evidence.map((e, i) => (
              <EvidenceBadge key={i} level={e.level} title={`${e.level}:${e.source}`}>
                {e.level}
                <span className="font-sans opacity-70">·{e.source}</span>
              </EvidenceBadge>
            ))}
          </span>
        ) : null}
      </div>
    </Card>
  )
}
