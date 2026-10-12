import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePlayback } from '@/lib/usePlayback'
import { PLAYBACK_SPEEDS } from '@/constants/ui'

describe('usePlayback 回放控制', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('初始停在第 0 步、未播放，lastIndex = 步数-1', () => {
    const { result } = renderHook(() => usePlayback(10))
    expect(result.current.current).toBe(0)
    expect(result.current.playing).toBe(false)
    expect(result.current.lastIndex).toBe(9)
    expect(result.current.progress).toBe(0)
  })

  it('next/prev 在边界处夹紧，不会越界', () => {
    const { result } = renderHook(() => usePlayback(3))
    act(() => result.current.prev())
    expect(result.current.current).toBe(0)
    act(() => { result.current.next(); result.current.next() })
    expect(result.current.current).toBe(2)
    act(() => result.current.next())          // 已在末步
    expect(result.current.current).toBe(2)
    expect(result.current.progress).toBe(1)
  })

  it('goto 越界值被夹紧到 [0, lastIndex]，小数取整', () => {
    const { result } = renderHook(() => usePlayback(5))
    act(() => result.current.goto(99))
    expect(result.current.current).toBe(4)
    act(() => result.current.goto(-3))
    expect(result.current.current).toBe(0)
    act(() => result.current.goto(2.6))
    expect(result.current.current).toBe(3)
  })

  it('播放时按当前档位自动步进，到末步自动暂停', () => {
    const { result } = renderHook(() => usePlayback(3))
    expect(result.current.stepMs).toBe(PLAYBACK_SPEEDS[1].ms)  // 默认 1×
    act(() => result.current.togglePlay())
    expect(result.current.playing).toBe(true)

    act(() => { vi.advanceTimersByTime(PLAYBACK_SPEEDS[1].ms) })
    expect(result.current.current).toBe(1)
    act(() => { vi.advanceTimersByTime(PLAYBACK_SPEEDS[1].ms) })
    expect(result.current.current).toBe(2)
    // 末步之后不再前进，且自动停下（复盘不循环）
    act(() => { vi.advanceTimersByTime(PLAYBACK_SPEEDS[1].ms * 3) })
    expect(result.current.current).toBe(2)
    expect(result.current.playing).toBe(false)
  })

  it('已在末步时再按播放会从头开始', () => {
    const { result } = renderHook(() => usePlayback(3))
    act(() => result.current.goto(2))
    act(() => result.current.togglePlay())
    expect(result.current.current).toBe(0)
    expect(result.current.playing).toBe(true)
  })

  it('切档位立即改变每步停留时长；cycleSpeed 循环到 0.5×', () => {
    const { result } = renderHook(() => usePlayback(4))
    act(() => result.current.setSpeedIndex(3))            // 4×
    expect(result.current.stepMs).toBe(PLAYBACK_SPEEDS[3].ms)
    act(() => result.current.cycleSpeed())                // 回到 0.5×
    expect(result.current.speedIndex).toBe(0)
    expect(result.current.stepMs).toBe(PLAYBACK_SPEEDS[0].ms)
  })

  it('步数变化（切换对局）时复位到第 0 步并暂停', () => {
    const { result, rerender } = renderHook(({ n }: { n: number }) => usePlayback(n), {
      initialProps: { n: 10 },
    })
    act(() => result.current.goto(7))
    expect(result.current.current).toBe(7)
    rerender({ n: 3 })
    expect(result.current.current).toBe(0)
    expect(result.current.playing).toBe(false)
  })

  it('卸载后不再触发定时器（无 act 警告 / 无内存泄漏）', () => {
    const { result, unmount } = renderHook(() => usePlayback(5))
    act(() => result.current.togglePlay())
    unmount()
    expect(() => act(() => { vi.advanceTimersByTime(5000) })).not.toThrow()
  })
})
