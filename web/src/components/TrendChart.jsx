import React, { useMemo } from 'react'
import { Card } from './ui.jsx'
import { safeMax } from '../utils/format.js'

/**
 * 全局趋势：费用曲线 + 耐久 + 每步耗时，横轴是步序，点任意位置跳到那一步。
 * 纯手写 SVG，不引图表库（mock 数据量小，引依赖不划算）。
 */
export default function TrendChart({ steps, current, onJump }) {
  const W = 1000
  const H = 150
  const PAD_L = 34
  const PAD_R = 34
  const PAD_T = 14
  const PAD_B = 22

  const model = useMemo(() => {
    const n = steps.length
    if (!n) return null
    const x = (i) => (n === 1 ? (PAD_L + (W - PAD_L - PAD_R) / 2) : PAD_L + (i * (W - PAD_L - PAD_R)) / (n - 1))

    // 费用取"决策时读数"与"执行后读数"的最大值做纵轴上限，保证两条线都在框内
    const costBefore = steps.map((s) => Number(s.state?.cost?.current ?? 0))
    const costAfter = steps.map((s) => Number(s.after?.cost ?? s.state?.cost?.current ?? 0))
    const life = steps.map((s) => Number(s.state?.lifePoints ?? s.after?.life ?? 0))
    const costLimit = Number(steps[0]?.state?.cost?.limit ?? 0)
    const maxCost = Math.max(safeMax(costBefore.concat(costAfter)), 10)
    const maxLife = Math.max(safeMax(life), 1)
    const lat = steps.map((s) => Object.values(s.latencyMs || {}).reduce((a, b) => a + (Number(b) || 0), 0))
    const maxLat = Math.max(safeMax(lat), 0.001)

    const yCost = (v) => PAD_T + (1 - v / maxCost) * (H - PAD_T - PAD_B)
    const yLife = (v) => PAD_T + (1 - v / maxLife) * (H - PAD_T - PAD_B)
    const path = (arr, yf) => arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${yf(v).toFixed(1)}`).join(' ')

    return { n, x, costBefore, costAfter, life, lat, maxCost, maxLife, maxLat, yCost, yLife, path, costLimit }
  }, [steps])

  if (!model) return null
  const { n, x, costAfter, costBefore, life, lat, maxCost, maxLife, maxLat, yCost, yLife, path } = model

  return (
    <Card
      title="全局趋势"
      extra={
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <span className="flex items-center gap-1"><i className="h-[2px] w-4 rounded" style={{ backgroundColor: '#22d3ee' }} />费用(执行后)</span>
          <span className="flex items-center gap-1"><i className="h-[2px] w-4 rounded" style={{ backgroundColor: '#34d399' }} />耐久</span>
          <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-sm" style={{ backgroundColor: '#fbbf24' }} />本步耗时</span>
        </div>
      }
      bodyClass="p-2"
    >
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[150px] w-full" role="img" aria-label="费用、耐久与耗时趋势">
        {/* 横向网格 + 左轴刻度 */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const y = PAD_T + f * (H - PAD_T - PAD_B)
          return (
            <g key={f}>
              <line x1={PAD_L} x2={W - PAD_R} y1={y} y2={y} stroke="#1e2a38" strokeWidth="1" />
              <text x={PAD_L - 6} y={y + 3.5} textAnchor="end" fontSize="9" fill="#475569" fontFamily="monospace">
                {Math.round(maxCost * (1 - f))}
              </text>
              <text x={W - PAD_R + 6} y={y + 3.5} textAnchor="start" fontSize="9" fill="#475569" fontFamily="monospace">
                {Math.round(maxLife * (1 - f))}
              </text>
            </g>
          )
        })}

        {/* 每步耗时：底部柱 */}
        {lat.map((v, i) => {
          const h = Math.max(1.5, (v / maxLat) * 26)
          const bw = Math.max(3, Math.min(18, (W - PAD_L - PAD_R) / Math.max(n, 1) - 6))
          return (
            <rect
              key={`lat-${i}`}
              x={x(i) - bw / 2}
              y={H - PAD_B - h}
              width={bw}
              height={h}
              rx="1.5"
              fill="#fbbf24"
              opacity={i === current ? 0.95 : 0.35}
            />
          )
        })}

        {/* 费用（决策时，浅色虚线）与执行后（实线） */}
        <path d={path(costBefore, yCost)} fill="none" stroke="#22d3ee" strokeOpacity="0.35" strokeWidth="1.5" strokeDasharray="4 3" />
        <path d={path(costAfter, yCost)} fill="none" stroke="#22d3ee" strokeWidth="2" />
        <path d={path(life, yLife)} fill="none" stroke="#34d399" strokeWidth="2" />

        {/* 数据点 + 命中区 */}
        {steps.map((s, i) => (
          <g key={s.step ?? i} onClick={() => onJump?.(i)} style={{ cursor: 'pointer' }}>
            <rect x={x(i) - (W - PAD_L - PAD_R) / Math.max(n - 1, 1) / 2} y={0} width={(W - PAD_L - PAD_R) / Math.max(n - 1, 1)} height={H} fill="transparent" />
            {i === current ? (
              <line x1={x(i)} x2={x(i)} y1={PAD_T - 6} y2={H - PAD_B} stroke="#22d3ee" strokeWidth="1" strokeDasharray="3 3" opacity="0.8" />
            ) : null}
            <circle cx={x(i)} cy={yCost(costAfter[i])} r={i === current ? 4.5 : 3} fill="#0c1119" stroke="#22d3ee" strokeWidth="2" />
            <circle cx={x(i)} cy={yLife(life[i])} r={i === current ? 4 : 2.6} fill="#0c1119" stroke="#34d399" strokeWidth="2" />
            <text x={x(i)} y={H - 6} textAnchor="middle" fontSize="9" fill={i === current ? '#67e8f9' : '#475569'} fontFamily="monospace">
              {s.step ?? i + 1}
            </text>
          </g>
        ))}
      </svg>
    </Card>
  )
}
