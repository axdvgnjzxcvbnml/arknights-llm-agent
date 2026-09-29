// @ts-nocheck
import React from 'react'
import { Card, Empty } from '@/components/replay/ui'
import { LATENCY_STAGES } from '@/constants/ui.js'
import { fmtMs, safeMax } from '@/lib/utils'

/**
 * 每步耗时分解：感知 -> 知识检索 -> 慢思考 -> 桥接 -> 快反应 -> 执行。
 * 只渲染后端真的给了的阶段（mock 链路里 perceive_ms 由 env 内部计时，可能缺席）。
 *
 * 注意：mock 全链路在 CPU 上跑，各阶段基本是亚毫秒级；真机/V100 接入后
 * 这里会显示真实的推理延迟（慢思考通常是主要开销）。
 */
export default function LatencyPanel({ step }) {
  const lat = step.latencyMs || {}
  const known = LATENCY_STAGES.filter((s) => lat[s.key] !== undefined && lat[s.key] !== null)
  // 后端将来若新增阶段（例如 vlm_ms），也要能显示出来，不被常量表卡死
  const extra = Object.keys(lat)
    .filter((k) => !LATENCY_STAGES.some((s) => s.key === k))
    .map((k) => ({ key: k, cn: k, hint: '后端新增阶段', color: '#64748b' }))
  const stages = known.concat(extra)
  const total = stages.reduce((a, s) => a + (Number(lat[s.key]) || 0), 0)
  const max = safeMax(stages.map((s) => Number(lat[s.key]) || 0)) || 1

  return (
    <Card
      title="本步耗时分解"
      extra={<span className="font-mono text-[11px] text-slate-400">合计 {fmtMs(total, 2)}</span>}
    >
      {stages.length ? (
        <>
          <ul className="space-y-1.5">
            {stages.map((s) => {
              const v = Number(lat[s.key]) || 0
              return (
                <li key={s.key} className="grid grid-cols-[76px_minmax(0,1fr)_66px] items-center gap-2" title={`${s.hint}（${s.key}）`}>
                  <span className="truncate text-[11px] text-slate-400">{s.cn}</span>
                  <span className="block h-[7px] w-full overflow-hidden rounded-full bg-ink-700/70">
                    <span
                      className="block h-full rounded-full transition-[width] duration-300"
                      style={{ width: `${Math.max((v / max) * 100, v > 0 ? 1.5 : 0)}%`, backgroundColor: s.color }}
                    />
                  </span>
                  <span className="text-right font-mono text-[11px] text-slate-300">{fmtMs(v, 2)}</span>
                </li>
              )
            })}
          </ul>
          {/* 占比条：一眼看出时间花在哪一段 */}
          <div className="mt-2.5 flex h-2 w-full overflow-hidden rounded-full bg-ink-800" title="各阶段占比">
            {stages.map((s) => {
              const v = Number(lat[s.key]) || 0
              const pct = total > 0 ? (v / total) * 100 : 0
              return pct > 0 ? <span key={s.key} style={{ width: `${pct}%`, backgroundColor: s.color }} /> : null
            })}
          </div>
          <p className="mt-2 text-[11px] leading-snug text-slate-500">
            mock 链路跑在 CPU 上、无真实模型推理，各阶段多为亚毫秒级；接入 V100 真实推理后此处即为实测延迟。
          </p>
        </>
      ) : (
        <Empty>本步没有延迟数据</Empty>
      )}
    </Card>
  )
}
