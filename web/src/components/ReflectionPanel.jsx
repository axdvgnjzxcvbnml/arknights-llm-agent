import React from 'react'
import { Card, Empty } from './ui.jsx'
import { verdictMeta } from '../constants/ui.js'
import { fmtSigned, rewardColor } from '../utils/format.js'

/** 本步结果：奖励增量 + 自我反思（喂给下一步慢思考的 adjustment）。 */
export default function ReflectionPanel({ step }) {
  const rf = step.reflection
  const items = step.reward?.items || []
  const delta = Number(step.reward?.stepReward || 0)
  const v = verdictMeta(rf?.verdict)

  return (
    <Card
      title="本步奖励与自我反思"
      extra={
        <span className="font-mono text-[12px] font-semibold" style={{ color: rewardColor(delta) }}>
          {fmtSigned(delta)}
        </span>
      }
    >
      <div className="card-title mb-1">奖励项 reward_items</div>
      {items.length ? (
        <ul className="space-y-1">
          {items.map((it, i) => (
            <li key={i} className="flex items-baseline gap-2 rounded border border-ink-700/70 bg-ink-850/50 px-2 py-1">
              <span className="w-16 shrink-0 font-mono text-[11px] text-slate-400">{it.name}</span>
              <span className="w-14 shrink-0 font-mono text-[12px]" style={{ color: rewardColor(it.delta) }}>
                {fmtSigned(it.delta)}
              </span>
              <span className="min-w-0 flex-1 text-[12px] text-slate-400">{it.why}</span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>本步无奖励变化（未漏怪、费用未溢出）</Empty>
      )}

      <div className="card-title mt-3 mb-1">自我反思 reflection</div>
      {rf ? (
        <div className="rounded-md border px-2.5 py-2" style={{ borderColor: `${v.color}44`, backgroundColor: `${v.color}0d` }}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip font-mono" style={{ color: v.color, borderColor: `${v.color}66`, backgroundColor: `${v.color}1a` }}>
              {rf.verdict} · {v.cn}
            </span>
            <span className="font-mono text-[11px] text-slate-500">conf {Number(rf.confidence ?? 0).toFixed(2)}</span>
            <span className="ml-auto font-mono text-[10px] text-slate-600">{rf.decisionId}</span>
          </div>
          {rf.issues?.length ? (
            <ul className="mt-1.5 space-y-0.5">
              {rf.issues.map((s, i) => (
                <li key={i} className="text-[12px] text-amber-200/90">· 问题：{s}</li>
              ))}
            </ul>
          ) : null}
          {rf.adjustment ? (
            <p className="mt-1 text-[12px] leading-relaxed text-slate-300">
              <span className="kv-label mr-1">修正</span>
              {rf.adjustment}
            </p>
          ) : null}
        </div>
      ) : (
        <Empty>本步未产生反思记录</Empty>
      )}
    </Card>
  )
}
