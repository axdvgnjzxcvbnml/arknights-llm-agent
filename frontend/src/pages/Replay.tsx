import { useEffect, useMemo, useState } from 'react'
import { useEpisode } from '@/lib/useEpisode'
import { usePlayback } from '@/lib/usePlayback'
import EpisodeHeader from '@/components/replay/EpisodeHeader'
import EpisodePicker from '@/components/replay/EpisodePicker'
import PlaybackControls from '@/components/replay/PlaybackControls'
import TimelineRail from '@/components/replay/TimelineRail'
import TrendChart from '@/components/replay/TrendChart'
import RewardPanel from '@/components/replay/RewardPanel'
import StepDetail from '@/components/replay/StepDetail'
import RawLogDrawer from '@/components/replay/RawLogDrawer'
import EvidenceLegend from '@/components/replay/EvidenceLegend'
import { ErrorBlock, Spinner } from '@/components/replay/ui'
import { isTypingTarget } from '@/lib/utils'

export default function App() {
  const { index, episodes, generatedAt, episodeId, selectEpisode, doc, episode, steps, retry } = useEpisode()
  const playback = usePlayback(steps.length)
  const [logsOpen, setLogsOpen] = useState(false)
  const [legendOpen, setLegendOpen] = useState(false)

  const step = steps[playback.current] || null

  /** 全体步骤里出现过的干员名 -> 职业/费用，用来给已部署干员上色（部署后手牌就没有它了） */
  const roster = useMemo(() => {
    const m = new Map()
    for (const s of steps) {
      for (const c of s.state?.operatorCards || []) {
        if (!m.has(c.name)) m.set(c.name, { operatorClass: c.operatorClass, cost: c.cost })
      }
    }
    return m
  }, [steps])

  // 键盘快捷键：空格播放/暂停，←/→ 单步，Home/End 首尾，L 原始日志
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target as HTMLElement | null) || e.metaKey || e.ctrlKey || e.altKey) return
      switch (e.key) {
        case ' ':
          e.preventDefault()
          playback.togglePlay()
          break
        case 'ArrowRight':
          e.preventDefault()
          playback.next()
          break
        case 'ArrowLeft':
          e.preventDefault()
          playback.prev()
          break
        case 'Home':
          playback.goto(0)
          break
        case 'End':
          playback.goto(playback.lastIndex)
          break
        case 'l':
        case 'L':
          setLogsOpen((v) => !v)
          break
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [playback])

  return (
    <div className="min-h-screen">
      <EpisodeHeader
        episode={episode}
        generatedAt={generatedAt}
        onOpenLogs={() => setLogsOpen(true)}
        onOpenLegend={() => setLegendOpen(true)}
      />

      <main className="mx-auto max-w-[1680px] px-4 py-4">
        {doc.error ? <ErrorBlock error={doc.error} onRetry={retry} /> : null}
        {index.error && !doc.error ? <ErrorBlock error={index.error} onRetry={retry} /> : null}

        {doc.loading || !episode ? (
          !doc.error ? <Spinner label="加载对局数据…" /> : null
        ) : (
          <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
            {/* 左栏：对局切换 + 播放控制 + 时间轴 */}
            <aside className="space-y-3 xl:sticky xl:top-[132px] xl:self-start">
              <EpisodePicker
                episodes={episodes}
                currentId={episodeId}
                onSelect={selectEpisode}
                loading={index.loading}
              />
              <PlaybackControls playback={playback} step={step} stepsCount={steps.length} />
              <TimelineRail steps={steps} current={playback.current} onSelect={playback.goto} />
              <div className="card px-3 py-2 text-[11px] leading-relaxed text-slate-500">
                <span className="text-slate-400">快捷键</span>：空格 播放/暂停 · ← → 单步 · Home/End 首尾 · L 原始日志
              </div>
            </aside>

            {/* 右栏：全局趋势 + 奖励 + 当前步详情 */}
            <div className="min-w-0 space-y-3">
              <TrendChart steps={steps} current={playback.current} onJump={playback.goto} />
              <RewardPanel episode={episode} stepRewards={steps} onJump={playback.goto} />
              {step ? (
                <StepDetail step={step} map={episode.map} roster={roster} />
              ) : (
                <div className="card p-6 text-center text-sm text-slate-500">该对局没有步骤数据</div>
              )}
            </div>
          </div>
        )}
      </main>

      <RawLogDrawer open={logsOpen} onClose={() => setLogsOpen(false)} />

      {legendOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-[2px]"
          onClick={() => setLegendOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="证据分级图例"
        >
          <div className="card max-h-[86vh] w-full max-w-3xl overflow-auto p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-100">证据分级（evidence level）</h2>
                <p className="mt-1 text-[12px] leading-relaxed text-slate-400">
                  取值与后端 <code className="rounded bg-ink-800 px-1 font-mono text-[11px]">agent/output_schema.py</code> 的
                  <code className="ml-1 rounded bg-ink-800 px-1 font-mono text-[11px]">EvidenceLevel</code> 一致。
                  其中 <b className="text-slate-200">retrieved / inferred / estimated</b> 一律不是事实判断，
                  界面上用虚线边框标注，复盘时不要当成确定结论引用。
                </p>
              </div>
              <button type="button" className="btn shrink-0" onClick={() => setLegendOpen(false)}>
                关闭 ✕
              </button>
            </div>
            <EvidenceLegend compact />
          </div>
        </div>
      ) : null}
    </div>
  )
}
