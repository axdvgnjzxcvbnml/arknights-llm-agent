// @ts-nocheck
import React from 'react'
import { Card, Empty } from '@/components/replay/ui'
import EvidenceBadge from './EvidenceBadge.jsx'
import { spawnSourceToLevel } from '@/constants/evidence.js'

/**
 * 敌情：场上敌人（observed）+ 波次时间轴（spawn_plan）。
 * 每条都带证据分级：cv = 视觉确认；estimated = 均匀估算（校准前不可当事实）。
 */
export default function EnemyPanel({ step }) {
  const st = step.state
  const enemies = st.enemiesOnField || []
  const plan = st.spawnPlan || []
  const t = Number(step.elapsedSec) || 0
  const total = enemies.reduce((a, e) => a + (e.observedCount || 0), 0)

  return (
    <Card
      title="敌情与波次"
      extra={<span className="font-mono text-[11px] text-slate-500">场上 {total} 个 · 波次 {plan.length} 组</span>}
    >
      <div className="card-title mb-1.5">当前场上</div>
      {enemies.length ? (
        <ul className="space-y-1">
          {enemies.map((e, i) => (
            <li key={i} className="flex items-center gap-2 rounded-md border border-ink-700/70 bg-ink-850/50 px-2 py-1.5">
              <span className="text-[13px] font-medium text-slate-100">{e.name}</span>
              <span className="chip border-rose-400/40 bg-rose-400/10 font-mono text-rose-300">×{e.observedCount}</span>
              {e.positionHint ? <span className="text-[11px] text-slate-500">{e.positionHint}</span> : null}
              <span className="ml-auto"><EvidenceBadge level={spawnSourceToLevel(e.source)} /></span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>暂无敌人出现</Empty>
      )}

      <div className="card-title mt-3 mb-1.5">波次时间轴（spawn_plan）</div>
      {plan.length ? (
        <ol className="relative space-y-1.5 border-l border-ink-700 pl-3">
          {plan.map((s, i) => {
            const passed = s.expectedTimeSec <= t
            const level = spawnSourceToLevel(s.confirmedBy)
            return (
              <li key={i} className="relative">
                <span
                  className="absolute -left-[17px] top-1.5 h-2 w-2 rounded-full border"
                  style={{
                    borderColor: passed ? '#fb7185' : '#3d5068',
                    backgroundColor: passed ? '#fb7185' : 'transparent',
                  }}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-[13px] ${passed ? 'text-slate-100' : 'text-slate-400'}`}>{s.enemy}</span>
                  <span className="chip border-ink-600 bg-ink-800 font-mono text-slate-400">×{s.count}</span>
                  <span className="font-mono text-[11px] text-slate-500">@t={s.expectedTimeSec}s</span>
                  <span className={`text-[10px] ${passed ? 'text-rose-300' : 'text-slate-600'}`}>
                    {passed ? '已到时刻' : `还有 ${(s.expectedTimeSec - t).toFixed(0)}s`}
                  </span>
                  <span className="ml-auto flex items-center gap-1">
                    {s.appeared ? <span className="chip border-emerald-400/40 bg-emerald-400/10 text-emerald-300">已确认出现</span> : null}
                    <EvidenceBadge level={level} />
                  </span>
                </div>
              </li>
            )
          })}
        </ol>
      ) : (
        <Empty>无波次数据</Empty>
      )}

      {st.vlm ? (
        <div className="mt-3 rounded-md border border-violet-400/30 bg-violet-400/5 p-2">
          <div className="flex items-center gap-2">
            <span className="card-title">VLM 局势判断</span>
            <EvidenceBadge level={st.vlm.level || 'inferred'} />
            <span className="ml-auto font-mono text-[10px] text-slate-500">
              {st.vlm.analyzer} · conf {(st.vlm.confidence ?? 0).toFixed(2)}
            </span>
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-slate-300">{st.vlm.situation}</p>
          {st.vlm.strategicAdvice ? (
            <p className="mt-1 text-[12px] leading-relaxed text-violet-200/90">
              <span className="text-slate-500">建议：</span>
              {st.vlm.strategicAdvice}
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}
