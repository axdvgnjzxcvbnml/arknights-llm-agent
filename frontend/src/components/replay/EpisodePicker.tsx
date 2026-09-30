import { outcomeMeta } from '@/constants/ui'
import { fmtSec, fmtSigned, rewardColor } from '@/lib/utils'
import { Card } from '@/components/replay/ui'
import type { EpisodeSummary } from '@/types/episode'

/** 对局切换：数据来自 GET /api/episodes（mock: episodes.json） */
export interface EpisodePickerProps {
  episodes: EpisodeSummary[]
  currentId: string | null
  onSelect: (id: string) => void
  loading?: boolean
}

export default function EpisodePicker({ episodes, currentId, onSelect, loading }: EpisodePickerProps) {
  return (
    <Card title="对局列表" bodyClass="p-2">
      {loading ? (
        <div className="px-2 py-3 text-xs text-slate-500">加载中…</div>
      ) : (
        <ul className="space-y-1.5">
          {episodes.map((ep) => {
            const oc = outcomeMeta(ep.outcome)
            const active = ep.id === currentId
            return (
              <li key={ep.id}>
                <button
                  type="button"
                  onClick={() => onSelect(ep.id)}
                  className={`w-full rounded-md border px-2.5 py-2 text-left transition ${
                    active
                      ? 'border-cyan-400/50 bg-cyan-400/8'
                      : 'border-ink-700/70 bg-ink-850/50 hover:border-ink-500'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`truncate text-[13px] font-medium ${active ? 'text-cyan-200' : 'text-slate-200'}`}>
                      {ep.title || ep.id}
                    </span>
                    <span
                      className="shrink-0 rounded border px-1.5 py-px text-[10px] font-semibold"
                      style={{ color: oc.color, borderColor: `${oc.color}55`, backgroundColor: `${oc.color}14` }}
                    >
                      {ep.outcomeLabel || oc.cn}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 font-mono text-[11px] text-slate-500">
                    <span>{ep.stepCount} 步</span>
                    <span>·</span>
                    <span>{fmtSec(ep.durationSec, 3)}</span>
                    <span>·</span>
                    <span style={{ color: rewardColor(ep.totalReward) }}>{fmtSigned(ep.totalReward, 0)}</span>
                  </div>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
