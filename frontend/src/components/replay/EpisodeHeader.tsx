import { dataSource } from '@/api/episode'
import { outcomeMeta } from '@/constants/ui'
import { fmtNum, fmtPct, fmtSec, fmtSigned, rewardColor } from '@/lib/utils'
import { Stat } from '@/components/replay/ui'
import type { EpisodeDto } from '@/types/episode'

/**
 * 顶部汇总条：一眼看清这局的结果、步数、耗时与奖励。
 * 数据全部来自 GET /api/episode/{id}（mock 模式下为 episodes.json / ep-*.json 的 episode 段）。
 */
export interface EpisodeHeaderProps {
  episode: EpisodeDto | null
  generatedAt?: string
  onOpenLogs?: () => void
  onOpenLegend?: () => void
}

export default function EpisodeHeader({ episode, generatedAt, onOpenLogs, onOpenLegend }: EpisodeHeaderProps) {
  if (!episode) return null
  const oc = outcomeMeta(episode.outcome)
  const { reward, totals } = episode
  const lat = totals?.latencySumMs || {}
  const sumLatency = Object.values(lat).reduce((a, b) => a + (Number(b) || 0), 0)

  return (
    <header className="sticky top-0 z-30 border-b border-ink-700/80 bg-ink-950/92 backdrop-blur">
      <div className="mx-auto max-w-[1680px] px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-sm font-bold"
                style={{ color: oc.color, borderColor: `${oc.color}66`, backgroundColor: `${oc.color}1a` }}
              >
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: oc.color }} />
                {episode.outcomeLabel || oc.cn}
              </span>
              <h1 className="truncate text-base font-semibold text-slate-100">
                {episode.title || `对局回放 · ${episode.stageId}`}
              </h1>
              <span className="chip border-ink-600 bg-ink-800 text-slate-400 font-mono">
                关卡 {episode.stageId}
              </span>
              <span className="chip border-ink-600 bg-ink-800 text-slate-400 font-mono">
                backend={episode.backend}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
              <span>
                数据源：
                <span className="font-mono text-slate-400">{dataSource.mode}</span>
                <span className="ml-1 font-mono">{dataSource.base}</span>
              </span>
              {generatedAt ? <span>生成于 {generatedAt}</span> : null}
              {episode.source ? <span>{episode.source}</span> : null}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="btn" onClick={onOpenLegend}>
              证据分级图例
            </button>
            <button type="button" className="btn" onClick={onOpenLogs}>
              原始日志
            </button>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 lg:grid-cols-8">
          <Stat label="总步数" value={episode.stepCount} unit={`/${episode.maxSteps ?? '—'} 上限`} />
          <Stat label="总耗时（墙钟）" value={fmtSec(episode.durationSec, 3)} hint="真实运行墙钟时间，mock 链路极快" />
          <Stat label="对局时间" value={fmtSec(episode.gameTimeSec, 0)} hint={`每步代表 ${fmtSec(episode.stepDtSec, 1)} 对局时间`} />
          <Stat
            label="总奖励"
            value={fmtSigned(reward.total)}
            color={rewardColor(reward.total)}
            hint={reward.summaryLine}
          />
          <Stat
            label="目标耐久"
            value={`${reward.lifeStart ?? '—'} → ${reward.lifeEnd ?? '—'}`}
            color={reward.leaked > 0 ? '#fb7185' : '#34d399'}
            hint={`漏怪 ${reward.leaked} 点`}
          />
          <Stat label="漏怪" value={reward.leaked} unit="点" color={reward.leaked > 0 ? '#fb7185' : '#94a3b8'} />
          <Stat
            label="动作成功"
            value={`${totals.actionsSucceeded}/${totals.actionsTotal}`}
            color={totals.actionsFailed ? '#fbbf24' : '#34d399'}
            hint={`失败 ${totals.actionsFailed} 个`}
          />
          <Stat
            label="平均置信度"
            value={fmtPct(totals.avgConfidence)}
            hint={`各阶段延迟合计 ${fmtNum(sumLatency, 1)}ms`}
          />
        </div>

        {reward.summaryLine ? (
          <p className="mt-2 truncate font-mono text-[11px] text-slate-500" title={reward.summaryLine}>
            奖励：{reward.summaryLine}
          </p>
        ) : null}
      </div>
    </header>
  )
}
