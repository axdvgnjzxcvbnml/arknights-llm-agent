// @ts-nocheck
import React, { useMemo } from 'react'
import { Card, Empty } from '@/components/replay/ui'
import { classColor, DIRECTION_ARROW, DIRECTION_CN } from '@/constants/ui.js'

/**
 * 10x10 地图：拓扑（terrain/deployable）来自对局级 episode.map，
 * 每步只叠加 occupiedCells 与已部署干员，所以能看出"格子是怎么被占掉的"。
 */
export default function MapGrid({ map, step, highlightAction, roster = new Map() }) {
  const cells = map?.cells || []
  const occupied = useMemo(() => new Set(step.state?.occupiedCells || []), [step])
  const deployed = step.state?.deployed || []
  const byName = useMemo(() => new Map(deployed.map((d) => [d.cellId, d])), [deployed])

  // 本步新部署的格子 -> 高亮（回放时能看出"这一步下在哪"）
  const targetCells = useMemo(() => {
    const set = new Set()
    for (const a of highlightAction?.actions || []) {
      if (a.action === 'deploy' && a.gridPos) set.add(a.gridPos)
      if (a.action === 'retreat' && a.operatorId) {
        const d = deployed.find((x) => x.name === a.operatorId)
        if (d?.cellId) set.add(d.cellId)
      }
    }
    return set
  }, [highlightAction, deployed])

  if (!cells.length) return <Card title="地图"><Empty>无地图数据</Empty></Card>

  const cols = map.cols || Math.max(...cells.map((c) => c.col)) + 1
  const rows = map.rows || Math.max(...cells.map((c) => c.row)) + 1
  const grid = Array.from({ length: rows }, () => Array.from({ length: cols }, () => null))
  for (const c of cells) {
    if (grid[c.row]?.[c.col] !== undefined) grid[c.row][c.col] = c
  }

  const deployableFree = cells.filter((c) => c.deployable && !occupied.has(c.cellId))

  return (
    <Card
      title="地图与部署"
      extra={
        <span className="font-mono text-[11px] text-slate-500">
          {cols}×{rows} · 可部署 {deployableFree.length} 格
        </span>
      }
    >
      <div
        className="grid gap-[3px]"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        role="grid"
        aria-label={`关卡地图 ${cols}x${rows}`}
      >
        {grid.flatMap((row, r) =>
          row.map((cell, c) => {
            if (!cell) {
              return <div key={`${r}-${c}`} className="aspect-square rounded-[2px] bg-ink-950/60" />
            }
            const op = byName.get(cell.cellId)
            const isOcc = occupied.has(cell.cellId)
            const isTarget = targetCells.has(cell.cellId)
            const bg = !cell.deployable
              ? '#111823'
              : isOcc
                ? '#1e2a38'
                : '#16202c'
            const border = isTarget ? '#22d3ee' : cell.deployable ? '#2a3a4d' : '#16202c'
            return (
              <div
                key={cell.cellId}
                role="gridcell"
                title={`${cell.cellId} · ${cell.terrain === 'blocked' ? '不可部署' : '可部署'}${isOcc ? ' · 已占用' : ''}${op ? ` · ${op.name}（${DIRECTION_CN[op.direction] || op.direction}）` : ''}`}
                className="relative flex aspect-square items-center justify-center rounded-[3px] border text-[9px] transition"
                style={{
                  backgroundColor: bg,
                  borderColor: border,
                  borderWidth: isTarget ? 2 : 1,
                  boxShadow: isTarget ? '0 0 10px rgba(34,211,238,.45)' : undefined,
                }}
              >
                {op ? (
                  <span className="flex flex-col items-center leading-none">
                    <span className="font-medium" style={{ color: classColor(roster.get(op.name)?.operatorClass) || '#e2e8f0' }}>
                      {op.name.slice(0, 2)}
                    </span>
                    <span className="mt-px font-mono text-[9px] text-slate-400">{DIRECTION_ARROW[op.direction] || ''}</span>
                  </span>
                ) : (
                  <span className="font-mono text-[8px] text-slate-600">{cell.deployable ? cell.cellId : ''}</span>
                )}
                {isTarget && !op ? (
                  <span className="absolute inset-0 animate-pulse-soft rounded-[2px] bg-cyan-400/15" />
                ) : null}
              </div>
            )
          }),
        )}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm border" style={{ borderColor: '#2a3a4d', backgroundColor: '#16202c' }} />可部署</span>
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm border" style={{ borderColor: '#16202c', backgroundColor: '#111823' }} />不可部署</span>
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm border" style={{ borderColor: '#2a3a4d', backgroundColor: '#1e2a38' }} />已占用</span>
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm border-2" style={{ borderColor: '#22d3ee' }} />本步目标</span>
      </div>
    </Card>
  )
}
