import React from 'react'
import { Card, Empty } from './ui.jsx'
import { actionMeta, DIRECTION_ARROW, DIRECTION_CN } from '../constants/ui.js'
import { fmtMs, fmtPct } from '../utils/format.js'
import EvidenceBadge from './EvidenceBadge.jsx'

function actionText(a) {
  if (!a) return ''
  switch (a.action) {
    case 'deploy':
      return `部署 ${a.operatorId} → ${a.gridPos}${a.direction ? `（朝${DIRECTION_CN[a.direction] || a.direction}${DIRECTION_ARROW[a.direction] || ''}）` : ''}`
    case 'skill':
      return `${a.operatorId} 开启技能 S${a.skillId}`
    case 'retreat':
      return `撤退 ${a.operatorId}`
    case 'wait':
      return `等待 ${a.durationMs ?? 0}ms`
    default:
      return a.action
  }
}

/**
 * 执行链路：慢思考 plan -> 慢快桥接 -> 快反应 command（含被拦截动作）-> ADB 执行结果。
 * 这一段是"决策怎么变成操作"的完整证据链，ops 是实际下发的设备原语序列。
 */
export default function ActionPanel({ step }) {
  const ex = step.execute
  const cmd = step.command
  const bridge = step.bridge
  const planActions = step.decision?.plan?.actions || []
  const results = ex?.results || []

  return (
    <Card
      title="执行动作"
      extra={
        <div className="flex items-center gap-2">
          {ex ? (
            <span
              className="chip font-mono"
              style={{
                color: ex.failed ? '#fb7185' : '#34d399',
                borderColor: ex.failed ? '#fb718566' : '#34d39966',
                backgroundColor: ex.failed ? '#fb718514' : '#34d39914',
              }}
            >
              {ex.succeeded}/{ex.total} 成功
            </span>
          ) : null}
          {cmd ? <span className="chip border-ink-600 bg-ink-800 font-mono text-slate-400">{cmd.reactor}</span> : null}
        </div>
      }
    >
      {/* 链路：想 -> 桥 -> 快 -> 打 */}
      <div className="mb-3 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="chip border-violet-400/40 bg-violet-400/10 text-violet-200">
          慢思考 {planActions.length} 动作
        </span>
        <span className="text-slate-600">→</span>
        <span className="chip border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-200" title={bridge?.hint}>
          桥接 dim={bridge?.dim ?? '—'}
        </span>
        <span className="text-slate-600">→</span>
        <span className="chip border-pink-400/40 bg-pink-400/10 text-pink-200">
          快反应 conf {cmd ? Number(cmd.confidence ?? 0).toFixed(2) : '—'}
          {cmd ? ` · ${fmtMs(cmd.reactMs, 2)}` : ''}
        </span>
        <span className="text-slate-600">→</span>
        <span className="chip border-emerald-400/40 bg-emerald-400/10 text-emerald-200">ADB 执行</span>
        {bridge?.source ? <EvidenceBadge level="mock" title={`桥接来源：${bridge.source}`} /> : null}
      </div>

      {bridge?.hint ? (
        <p className="mb-2 rounded border border-ink-700/70 bg-ink-850/60 px-2 py-1.5 text-[12px] leading-relaxed text-slate-400">
          <span className="kv-label mr-1">战略意图</span>
          {bridge.hint}
        </p>
      ) : null}

      {results.length ? (
        <ul className="space-y-1.5">
          {results.map((r) => {
            const meta = actionMeta(r.action)
            const act = planActions[r.index] || cmd?.plan?.actions?.[r.index]
            return (
              <li
                key={r.index}
                className="rounded-md border px-2.5 py-2"
                style={{
                  borderColor: r.success ? `${meta.color}44` : '#fb718555',
                  backgroundColor: r.success ? `${meta.color}0a` : '#fb71850d',
                }}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[10px] text-slate-600">#{r.index}</span>
                  <span
                    className="chip font-mono"
                    style={{ color: meta.color, borderColor: `${meta.color}66`, backgroundColor: `${meta.color}1a` }}
                    title={meta.desc}
                  >
                    {meta.icon} {r.action} · {meta.cn}
                  </span>
                  <span className="text-[13px] text-slate-200">{actionText(act)}</span>
                  <span
                    className="ml-auto chip font-mono"
                    style={{
                      color: r.success ? '#34d399' : '#fb7185',
                      borderColor: r.success ? '#34d39966' : '#fb718566',
                      backgroundColor: r.success ? '#34d39914' : '#fb718514',
                    }}
                  >
                    {r.success ? '成功' : `失败(${r.status})`}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <span className="kv-label">设备原语</span>
                  {r.success ? (
                    (r.ops || []).map((op, i) => (
                      <React.Fragment key={i}>
                        {i > 0 ? <span className="text-slate-600">→</span> : null}
                        <span className="chip border-ink-600 bg-ink-800 font-mono text-[10px] text-slate-300">{op}</span>
                      </React.Fragment>
                    ))
                  ) : (
                    <span className="text-[11px] text-rose-300">{r.error || r.status}</span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      ) : (
        <Empty>本步没有可展示的执行结果</Empty>
      )}

      {cmd?.dropped?.length ? (
        <div className="mt-2 rounded-md border border-amber-400/35 bg-amber-400/5 px-2 py-1.5">
          <div className="kv-label mb-1">快通道拦截（当前不可执行）</div>
          <ul className="space-y-0.5">
            {cmd.dropped.map((d, i) => (
              <li key={i} className="text-[12px] text-amber-200/90">· {d}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {cmd?.note ? <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{cmd.note}</p> : null}
      {cmd ? <div className="mt-1 font-mono text-[10px] text-slate-600">{cmd.commandId} · 反应 {fmtMs(cmd.reactMs, 2)} · 置信 {fmtPct(cmd.confidence)}</div> : null}
    </Card>
  )
}
