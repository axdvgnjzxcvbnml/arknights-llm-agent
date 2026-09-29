// @ts-nocheck
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PLAYBACK_SPEEDS } from '../constants/ui.js'
import { clamp } from '@/lib/utils'

/**
 * 回放播放控制：当前步 / 播放暂停 / 速度 / 上一步下一步 / 进度。
 *
 * 播放到末尾会自动停下（不循环），符合"复盘"的使用习惯；
 * 想重看直接点回第一步或按 Home。
 */
export function usePlayback(total, { defaultSpeedIndex = 1 } = {}) {
  const count = Math.max(0, Number(total) || 0)
  const [current, setCurrent] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speedIndex, setSpeedIndex] = useState(defaultSpeedIndex)
  const timerRef = useRef(null)

  const lastIndex = Math.max(0, count - 1)
  const stepMs = PLAYBACK_SPEEDS[speedIndex]?.ms ?? 1200

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const goto = useCallback(
    (i) => setCurrent(clamp(Math.round(i), 0, lastIndex)),
    [lastIndex],
  )

  const next = useCallback(() => {
    setCurrent((c) => {
      const n = c + 1
      if (n > lastIndex) {
        setPlaying(false)
        return lastIndex
      }
      return n
    })
  }, [lastIndex])

  const prev = useCallback(() => setCurrent((c) => Math.max(0, c - 1)), [])

  const togglePlay = useCallback(() => {
    // 已停在末尾时再按播放 -> 从头开始
    if (!playing && current >= lastIndex) setCurrent(0)
    setPlaying((p) => !p)
  }, [playing, current, lastIndex])

  // 自动步进
  useEffect(() => {
    clearTimer()
    if (!playing || count === 0) return undefined
    timerRef.current = setTimeout(() => {
      setCurrent((c) => {
        if (c >= lastIndex) {
          setPlaying(false)
          return c
        }
        return c + 1
      })
    }, stepMs)
    return clearTimer
  }, [playing, current, count, lastIndex, stepMs, clearTimer])

  // 切换对局 / 步数变化时复位
  useEffect(() => {
    setCurrent(0)
    setPlaying(false)
  }, [count])

  useEffect(() => clearTimer, [clearTimer])

  const progress = useMemo(
    () => (lastIndex === 0 ? 1 : current / lastIndex),
    [current, lastIndex],
  )

  return {
    current,
    playing,
    speedIndex,
    stepMs,
    speeds: PLAYBACK_SPEEDS,
    lastIndex,
    progress,
    goto,
    next,
    prev,
    togglePlay,
    setPlaying,
    setSpeedIndex,
    cycleSpeed: () => setSpeedIndex((i) => (i + 1) % PLAYBACK_SPEEDS.length),
  }
}
