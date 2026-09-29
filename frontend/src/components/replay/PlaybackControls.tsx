// @ts-nocheck
import React from 'react'
import { fmtSec } from '@/lib/utils'

/** 回放控制条：播放/暂停、单步、跳首尾、速度、进度滑块。 */
export default function PlaybackControls({ playback, step, stepsCount }) {
  const { playing, current, lastIndex, progress, speeds, speedIndex, stepMs } = playback
  const cur = step || {}

  return (
    <div className="card p-2.5">
      <div className="flex items-center gap-1.5">
        <button type="button" className="btn px-2" onClick={() => playback.goto(0)} title="回到第 1 步（Home）" disabled={current === 0}>
          ⏮
        </button>
        <button type="button" className="btn px-2" onClick={playback.prev} title="上一步（←）" disabled={current === 0}>
          ◀
        </button>
        <button
          type="button"
          className={`btn flex-1 px-3 ${playing ? 'btn-active' : ''}`}
          onClick={playback.togglePlay}
          title="播放 / 暂停（空格）"
          disabled={stepsCount === 0}
        >
          {playing ? '❚❚ 暂停' : '▶ 播放'}
        </button>
        <button type="button" className="btn px-2" onClick={playback.next} title="下一步（→）" disabled={current >= lastIndex}>
          ▶
        </button>
        <button type="button" className="btn px-2" onClick={() => playback.goto(lastIndex)} title="跳到末步（End）" disabled={current >= lastIndex}>
          ⏭
        </button>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <input
          type="range"
          min={0}
          max={Math.max(lastIndex, 0)}
          step={1}
          value={current}
          onChange={(e) => playback.goto(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-ink-700 accent-cyan-400"
          style={{
            background: `linear-gradient(90deg, #22d3ee ${progress * 100}%, #1e2a38 ${progress * 100}%)`,
          }}
          aria-label="回放进度"
        />
        <span className="shrink-0 font-mono text-[11px] text-slate-400">
          {current + 1}/{stepsCount || 0}
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          {speeds.map((s, i) => (
            <button
              key={s.label}
              type="button"
              onClick={() => (playback.setSpeedIndex ? playback.setSpeedIndex(i) : playback.cycleSpeed())}
              className={`btn px-1.5 py-0.5 font-mono text-[11px] ${i === speedIndex ? 'btn-active' : ''}`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <span className="truncate font-mono text-[11px] text-slate-500" title="每步停留时长">
          t={fmtSec(cur.elapsedSec, 0)} · {stepMs}ms/步
        </span>
      </div>
    </div>
  )
}
