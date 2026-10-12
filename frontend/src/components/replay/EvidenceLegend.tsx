import { EVIDENCE_LEVELS } from '@/constants/evidence'
import EvidenceBadge from './EvidenceBadge'

export interface EvidenceLegendProps {
  /** 紧凑模式：多列网格（弹窗里用）；否则单列 */
  compact?: boolean
}

/** 证据分级图例：说明每级含义与可信度，避免读者把"推断"当"事实"。 */
export default function EvidenceLegend({ compact = false }: EvidenceLegendProps) {
  return (
    <div className={compact ? 'grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4' : 'space-y-2'}>
      {EVIDENCE_LEVELS.map((lv) => (
        <div
          key={lv.key}
          className={
            compact
              ? 'rounded-md border border-ink-700/70 bg-ink-850/60 p-2'
              : 'flex gap-2 rounded-md border border-ink-700/70 bg-ink-850/60 p-2'
          }
        >
          <div className="shrink-0">
            <EvidenceBadge level={lv.key} />
          </div>
          <div className="min-w-0">
            <div className="text-[12px] font-medium text-slate-200">
              {lv.cn}
              <span className="ml-1.5 text-[10px] text-slate-500">{lv.trust}</span>
            </div>
            <p className="mt-0.5 text-[11px] leading-snug text-slate-400">{lv.desc}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
