// @ts-nocheck
import React, { useEffect, useRef } from 'react'
import { actionMeta } from '@/constants/ui.js'
import { evidenceLineStyle } from '@/constants/evidence.js'
import { fmtMs, fmtSigned, rewardColor } from '@/lib/utils'

function dominantAction(step) {
  const actions = step?.execute?.results?.map((r) => r.action) || step?.decision?.plan?.actions?.map((a) => a.action) || []
  const meaningful = actions.find((a) => a !== 'wait')
  return meaningful || actions[0] || 'wait'
}

function stepOk(step) {
  const ex = step?.execute
  if (!ex) return true
  return ex.failed === 0 && ex.total > 0
}

/**
 * 左侧时间轴：每步一个节点，竖线颜色取该步"最主要的证据级别"，
 * 节点里给出 t、动作类型、费用、本步奖励，点击直接跳转。
 */
export default function TimelineRail({ steps, current, onSelect }) {
  const listRef = useRef(null)

  // 播放时让当前节点始终可见
  useEffect(() => {
    const box = listRef.current
    if (!box) return
    const el = box.querySelector(`[data-step-idx="${current}"]`)
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest' })
    }
  }, [current])

  if (!steps?.length) {
    return <div className="card p-3 text-xs text-slate-500">暂无步骤数据</div>
  }

  return (
    <div className="card flex min-h-0 flex-col">
      <header className="flex items-center justify-between border-b border-ink-700/70 px-3 py-2">
        <h2 className="card-title">决策时间轴</h2>
        <span className="font-mono text-[11px] text-slate-500">{steps.length} 步</span>
      </header>
      <ol ref={listRef} className="scrollbar-thin max-h-[52vh] min-h-0 overflow-y-auto p-2 lg:max-h-[calc(100vh-330px)]">
        {steps.map((s, i) => {
          const act = actionMeta(dominantAction(s))
          const active = i === current
          const ok = stepOk(s)
          const ev = s.evidence?.[0]?.level || 'mock'
          const latTotal = Object.values(s.latencyMs || {}).reduce((a, b) => a + (Number(b) || 0), 0)
          return (
            <li key={s.step ?? i} data-step-idx={i} className="relative">
              {i < steps.length - 1 ? (
                <span className="absolute left-[15px] top-8 h-[calc(100%-16px)] w-px" style={evidenceLineStyle(ev)} />
              ) : null}
              <button
                type="button"
                onClick={() => onSelect(i)}
                className={`relative flex w-full items-start gap-2 rounded-md border px-2 py-1.5 text-left transition ${
                  active
                    ? 'border-cyan-400/55 bg-cyan-400/10'
                    : 'border-transparent hover:border-ink-600 hover:bg-ink-850/70'
                }`}
              >
                <span
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border font-mono text-[10px] font-bold"
                  style={{
                    borderColor: active ? '#22d3ee' : `${act.color}88`,
                    backgroundColor: active ? '#22d3ee' : `${act.color}1f`,
                    color: active ? '#08131a' : act.color,
                  }}
                >
                  {s.step ?? i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-1">
                    <span className="truncate text-[12px] font-medium" style={{ color: active ? '#a5f3fc' : '#e2e8f0' }}>
                      <span style={{ color: act.color }}>{act.icon}</span> {act.cn}
                      {s.decision?.plan?.actions?.length > 1 ? ` ×${s.decision.plan.actions.length}` : ''}
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-slate-500">t={s.elapsedSec}s</span>
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-slate-400" title={s.reasoning?.summary}>
                    {s.reasoning?.summary || '—'}
                  </span>
                  <span className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-slate-500">
                    <span>费{s.state?.cost?.current ?? s.after?.cost ?? '?'}</span>
                    <span>耐{s.state?.lifePoints ?? s.after?.life ?? '?'}</span>
                    <span style={{ color: ok ? '#64748b' : '#fb7185' }}>{ok ? 'ok' : 'fail'}</span>
                    <span>{fmtMs(latTotal, 1)}</span>
                    {s.reward?.stepReward ? (
                      <span style={{ color: rewardColor(s.reward.stepReward) }}>{fmtSigned(s.reward.stepReward, 0)}</span>
                    ) : null}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
