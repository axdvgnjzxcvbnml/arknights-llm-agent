// @ts-nocheck
import React from 'react'
import EvidenceBadge from './EvidenceBadge.jsx'
import { Bar, Card } from '@/components/replay/ui'
import { readingSourceToLevel } from '@/constants/evidence.js'
import { fmtMs, fmtPct } from '@/lib/utils'

const COST_STATE_CN = { ok: '读数稳定', uncertain: '相邻帧不一致（OCR 抖动，勿据此决策）', missing: '本帧未读到数字' }

/**
 * 本步游戏状态：费用 / 耐久 / 部署位 / 对局时间。
 * 关键读数都带证据标签 —— 费用是 OCR 读数（cv）还是 mock 合成，界面上一眼能分辨。
 */
export default function StatePanel({ step }) {
  const st = step.state
  const cost = st.cost || {}
  const limit = cost.limit ?? 0
  const latTotal = Object.values(step.latencyMs || {}).reduce((a, b) => a + (Number(b) || 0), 0)
  const costLevel = readingSourceToLevel(cost.source)
  const life = st.lifePoints
  const deployUsed = st.deployUsed ?? st.deployed?.length ?? 0

  return (
    <Card
      title={`步 ${step.step} · 游戏状态（决策前）`}
      extra={
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-slate-500">t={step.elapsedSec}s</span>
          <span className="chip border-ink-600 bg-ink-800 font-mono text-slate-400" title="本步各阶段延迟合计">
            {fmtMs(latTotal, 1)}
          </span>
        </div>
      }
    >
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 lg:grid-cols-4">
        {/* 费用 */}
        <div>
          <div className="flex items-center justify-between">
            <span className="kv-label">费用 cost</span>
            <EvidenceBadge level={costLevel} title={`读数来源：${cost.source || '—'}（${COST_STATE_CN[cost.state] || ''}）`} />
          </div>
          <div className="mt-0.5 flex items-baseline gap-1">
            <span className="font-mono text-2xl font-bold text-cyan-300">{cost.current ?? '—'}</span>
            <span className="font-mono text-xs text-slate-500">/ {limit || '—'}</span>
            {cost.confidence ? (
              <span className="ml-auto font-mono text-[10px] text-slate-500">conf {fmtPct(cost.confidence)}</span>
            ) : null}
          </div>
          <Bar className="mt-1" value={cost.current ?? 0} max={limit || 1} color="#22d3ee" />
          <div className="mt-1 flex items-center justify-between text-[11px]">
            <span className={cost.state === 'ok' ? 'text-slate-500' : 'text-amber-300'}>
              {COST_STATE_CN[cost.state] || cost.state || '—'}
            </span>
            <span className="font-mono text-slate-500">执行后 {step.after?.cost ?? '—'}</span>
          </div>
        </div>

        {/* 耐久 */}
        <div>
          <div className="flex items-center justify-between">
            <span className="kv-label">目标耐久 life</span>
            {life === 0 ? <span className="chip border-rose-400/50 bg-rose-400/10 text-rose-300">归零</span> : null}
          </div>
          <div className="mt-0.5 flex items-baseline gap-1">
            <span className="font-mono text-2xl font-bold" style={{ color: life <= 0 ? '#fb7185' : life <= 1 ? '#fbbf24' : '#34d399' }}>
              {life ?? '—'}
            </span>
            <span className="text-xs text-slate-500">点</span>
            <span className="ml-auto font-mono text-[10px] text-slate-500">执行后 {step.after?.life ?? '—'}</span>
          </div>
          <div className="mt-1.5 flex gap-1">
            {Array.from({ length: Math.max(3, Number(life) || 0) }).map((_, i) => (
              <span
                key={i}
                className="h-2 flex-1 rounded-sm"
                style={{ backgroundColor: i < (life ?? 0) ? (life <= 1 ? '#fbbf24' : '#34d399') : '#1e2a38' }}
              />
            ))}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">每漏 1 点 -10 分</div>
        </div>

        {/* 部署位 */}
        <div>
          <div className="flex items-center justify-between">
            <span className="kv-label">部署位 deploy</span>
            <span className="font-mono text-[10px] text-slate-500">手牌 {st.operatorCards?.length ?? 0}</span>
          </div>
          <div className="mt-0.5 flex items-baseline gap-1">
            <span className="font-mono text-2xl font-bold text-slate-100">{deployUsed ?? '—'}</span>
            <span className="font-mono text-xs text-slate-500">/ {st.deployLimit ?? '—'}</span>
          </div>
          <Bar className="mt-1" value={deployUsed ?? 0} max={st.deployLimit || 1} color="#60a5fa" />
          <div className="mt-1 text-[11px] text-slate-500">已上场 {st.deployed?.length ?? 0} 名干员</div>
        </div>

        {/* 波次可信度 + 思考 */}
        <div>
          <div className="flex items-center justify-between">
            <span className="kv-label">波次时间轴</span>
            <EvidenceBadge level={st.timingSource === 'annotated' ? 'annotated' : 'estimated'} />
          </div>
          <div className="mt-0.5 font-mono text-sm text-slate-200">
            {st.timingSource === 'annotated' ? '人工标注' : '均匀估算'}
          </div>
          <div className="mt-1.5 space-y-0.5 text-[11px] text-slate-500">
            <div className="flex justify-between">
              <span>置信度</span>
              <span className="font-mono text-slate-300">{fmtPct(step.decision?.confidence, 0)}</span>
            </div>
            <div className="flex justify-between">
              <span>思考耗时</span>
              <span className="font-mono text-slate-300">{fmtMs(step.decision?.thoughtMs, 2)}</span>
            </div>
          </div>
        </div>
      </div>

      {st.notes?.length ? (
        <details className="mt-3 border-t border-ink-700/70 pt-2">
          <summary className="cursor-pointer text-[11px] text-slate-500 hover:text-slate-300">
            状态备注 {st.notes.length} 条（mock 合成 / 估算值声明）
          </summary>
          <ul className="mt-1.5 space-y-1">
            {st.notes.map((n, i) => (
              <li key={i} className="rounded border border-amber-400/25 bg-amber-400/5 px-2 py-1 text-[11px] leading-snug text-amber-200/85">
                {n}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </Card>
  )
}
