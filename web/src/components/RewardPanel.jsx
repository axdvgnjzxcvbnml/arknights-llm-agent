import React from 'react'
import { fmtSigned, rewardColor, safeMax } from '../utils/format.js'
import { Bar, Card, Empty } from './ui.jsx'

/** 奖励明细：win / leak / overcost 三类结算项 + 逐条 why。 */
export default function RewardPanel({ episode, stepRewards, onJump }) {
  if (!episode) return null
  const r = episode.reward
  const parts = [
    { name: '通关 win', delta: r.winBonus, why: r.winBonus ? '通关成功' : '未通关' },
    { name: '漏怪 leak', delta: r.leakPenalty, why: `漏怪 ${r.leaked} 点 × -10` },
    { name: '费用溢出 overcost', delta: r.overcostPenalty, why: `溢出 ${r.overcostSec}s × -1/s` },
  ]
  const maxAbs = safeMax(parts.map((p) => Math.abs(p.delta)))

  return (
    <Card
      title="奖励结算"
      extra={
        <span className="font-mono text-sm font-semibold" style={{ color: rewardColor(r.total) }}>
          总分 {fmtSigned(r.total)}
        </span>
      }
    >
      <div className="space-y-2">
        {parts.map((p) => (
          <div key={p.name} className="grid grid-cols-[132px_minmax(0,1fr)_64px] items-center gap-2">
            <span className="truncate text-[12px] text-slate-400">{p.name}</span>
            <Bar value={Math.abs(p.delta)} max={maxAbs || 1} color={rewardColor(p.delta)} height={6} />
            <span className="text-right font-mono text-[12px]" style={{ color: rewardColor(p.delta) }}>
              {fmtSigned(p.delta)}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 border-t border-ink-700/70 pt-2">
        <div className="card-title mb-1.5">逐条明细（items）</div>
        {r.items?.length ? (
          <ul className="space-y-1">
            {r.items.map((it, i) => (
              <li key={i} className="flex items-baseline gap-2 text-[12px]">
                <span className="w-16 shrink-0 font-mono text-slate-400">{it.name}</span>
                <span className="w-14 shrink-0 font-mono" style={{ color: rewardColor(it.delta) }}>
                  {fmtSigned(it.delta)}
                </span>
                <span className="min-w-0 flex-1 text-slate-400">{it.why}</span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>本局无扣分项</Empty>
        )}
      </div>

      {stepRewards?.length ? (
        <div className="mt-3 border-t border-ink-700/70 pt-2">
          <div className="card-title mb-1.5">逐步奖励</div>
          <div className="flex flex-wrap gap-1">
            {stepRewards.map((s, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onJump?.(i)}
                title={`第 ${s.step} 步：${fmtSigned(s.reward.stepReward)}`}
                className="rounded border px-1.5 py-0.5 font-mono text-[11px] transition hover:brightness-125"
                style={{
                  color: rewardColor(s.reward.stepReward),
                  borderColor: s.reward.stepReward ? `${rewardColor(s.reward.stepReward)}55` : '#1e2a38',
                  backgroundColor: s.reward.stepReward ? `${rewardColor(s.reward.stepReward)}14` : 'transparent',
                }}
              >
                {s.step}·{fmtSigned(s.reward.stepReward, 0)}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  )
}
