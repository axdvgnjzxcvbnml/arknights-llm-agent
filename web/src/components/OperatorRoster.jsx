import React from 'react'
import { Card, Empty, Bar } from './ui.jsx'
import { classColor, DIRECTION_ARROW, DIRECTION_CN } from '../constants/ui.js'
import { fmtPct } from '../utils/format.js'
import EvidenceBadge from './EvidenceBadge.jsx'

function ClassDot({ name }) {
  return <i className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: classColor(name) }} />
}

/**
 * 干员面板：手牌（可部署）/ 已部署（位置、朝向、血量、技能）三块。
 * 手牌卡带"费用是否够"的实时判定 —— 这是 Agent 决策依据 1 的来源。
 */
export default function OperatorRoster({ step }) {
  const st = step.state
  const cards = st.operatorCards || []
  const deployed = st.deployed || []
  const skills = st.skills || []
  const cost = st.cost?.current ?? 0
  const skillByOp = new Map()
  for (const s of skills) {
    if (!skillByOp.has(s.operator)) skillByOp.set(s.operator, [])
    skillByOp.get(s.operator).push(s)
  }

  return (
    <Card title="干员与技能" extra={<span className="font-mono text-[11px] text-slate-500">当前费用 {cost}</span>}>
      <div className="grid gap-3 lg:grid-cols-2">
        {/* 手牌 */}
        <div>
          <div className="card-title mb-1.5">手牌（可部署）· {cards.length}</div>
          {cards.length ? (
            <ul className="space-y-1">
              {cards.map((c) => {
                const affordable = cost >= c.cost
                return (
                  <li
                    key={`${c.name}-${c.slot}`}
                    className="flex items-center gap-2 rounded-md border px-2 py-1.5"
                    style={{
                      borderColor: affordable ? `${classColor(c.operatorClass)}55` : '#1e2a38',
                      backgroundColor: affordable ? `${classColor(c.operatorClass)}0d` : 'transparent',
                      opacity: c.available === false ? 0.55 : 1,
                    }}
                  >
                    <ClassDot name={c.operatorClass} />
                    <span className="text-[13px] font-medium text-slate-100">{c.name}</span>
                    <span className="chip border-ink-600 bg-ink-800 text-slate-400">{c.operatorClass || '—'}</span>
                    <span className="ml-auto flex items-center gap-1.5">
                      <span
                        className="font-mono text-[12px] font-semibold"
                        style={{ color: affordable ? '#22d3ee' : '#fb7185' }}
                        title={affordable ? `费用 ${cost} ≥ ${c.cost}，可部署` : `费用 ${cost} < ${c.cost}，不足`}
                      >
                        {c.cost}费
                      </span>
                      <span className="font-mono text-[10px] text-slate-600">槽{c.slot}</span>
                    </span>
                  </li>
                )
              })}
            </ul>
          ) : (
            <Empty>手牌已空（全部部署完毕）</Empty>
          )}
        </div>

        {/* 已部署 */}
        <div>
          <div className="card-title mb-1.5">已部署 · {deployed.length}</div>
          {deployed.length ? (
            <ul className="space-y-1">
              {deployed.map((d) => {
                const ops = skillByOp.get(d.name) || []
                return (
                  <li key={`${d.name}-${d.cellId}`} className="rounded-md border border-ink-700/70 bg-ink-850/50 px-2 py-1.5">
                    <div className="flex items-center gap-2">
                      <ClassDot name={(ops[0]?.operatorClass) || ''} />
                      <span className="text-[13px] font-medium text-slate-100">{d.name}</span>
                      <span className="chip border-ink-600 bg-ink-800 font-mono text-slate-400">
                        @{d.cellId}
                        {d.direction ? ` ${DIRECTION_ARROW[d.direction] || ''}${DIRECTION_CN[d.direction] || ''}` : ''}
                      </span>
                      <span className="ml-auto font-mono text-[11px]" style={{ color: (d.hpRatio ?? 1) > 0.5 ? '#34d399' : '#fb7185' }}>
                        HP {fmtPct(d.hpRatio ?? 1)}
                      </span>
                    </div>
                    {d.hpRatio !== null && d.hpRatio !== undefined ? (
                      <Bar className="mt-1" value={d.hpRatio ?? 0} max={1} color={(d.hpRatio ?? 1) > 0.5 ? '#34d399' : '#fb7185'} height={3} />
                    ) : null}
                    {ops.length ? (
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {ops.map((s, i) => (
                          <span key={i} className="flex items-center gap-1">
                            <span className="chip border-ink-600 bg-ink-800 font-mono text-[10px] text-slate-400">
                              {s.spText || `槽${s.slot}`}
                            </span>
                            {s.ready ? <span className="chip border-emerald-400/50 bg-emerald-400/10 text-emerald-300">可开启</span> : null}
                            {s.active ? <span className="chip border-cyan-400/50 bg-cyan-400/10 text-cyan-300">持续中</span> : null}
                            {!s.ready && !s.active ? <span className="text-[10px] text-slate-600">充能中</span> : null}
                            <EvidenceBadge level={s.source === 'cv' ? 'cv' : 'mock'} />
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          ) : (
            <Empty>尚无干员在场</Empty>
          )}
        </div>
      </div>
    </Card>
  )
}
