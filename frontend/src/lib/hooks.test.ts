import { describe, it, expect, vi } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { usePolling } from "@/lib/hooks"

describe("usePolling", () => {
  // 用真实 timers + 短 interval，避免 fake timers 与 async/await 的交互问题
  const SHORT_INTERVAL = 50

  it("初始状态 loading=true, data=null, error=null", () => {
    const fetcher = vi.fn().mockResolvedValue({ value: 1 })
    const { result } = renderHook(() => usePolling(fetcher, 10000))
    expect(result.current.loading).toBe(true)
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it("首次 fetcher 成功后设置 data 并 loading=false", async () => {
    const fetcher = vi.fn().mockResolvedValue({ value: 42 })
    const { result } = renderHook(() => usePolling(fetcher, 10000))

    await waitFor(() => {
      expect(result.current.data).toEqual({ value: 42 })
      expect(result.current.loading).toBe(false)
      expect(result.current.error).toBeNull()
    }, { timeout: 2000 })
  })

  it("fetcher 失败时设置 error", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("网络错误"))
    const { result } = renderHook(() => usePolling(fetcher, 10000))

    await waitFor(() => {
      expect(result.current.error).toBe("网络错误")
      expect(result.current.loading).toBe(false)
    }, { timeout: 2000 })
  })

  it("非 Error 类型的异常也能转为字符串", async () => {
    const fetcher = vi.fn().mockRejectedValue("字符串异常")
    const { result } = renderHook(() => usePolling(fetcher, 10000))

    await waitFor(() => {
      expect(result.current.error).toBe("字符串异常")
    }, { timeout: 2000 })
  })

  it("intervalMs 后触发下一次轮询", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce({ value: 1 })
      .mockResolvedValueOnce({ value: 2 })

    const { result } = renderHook(() => usePolling(fetcher, SHORT_INTERVAL))

    // 第一次
    await waitFor(() => expect(result.current.data).toEqual({ value: 1 }), { timeout: 2000 })

    // 第二次（等 interval 过去）
    await waitFor(() => expect(result.current.data).toEqual({ value: 2 }), { timeout: 2000 })

    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it("卸载后不再调用 fetcher", async () => {
    const fetcher = vi.fn().mockResolvedValue({ value: 1 })
    const { result, unmount } = renderHook(() => usePolling(fetcher, SHORT_INTERVAL))

    await waitFor(() => expect(result.current.data).toEqual({ value: 1 }), { timeout: 2000 })

    const callCountBeforeUnmount = fetcher.mock.calls.length
    unmount()

    // 等几个 interval，确认不再调用
    await new Promise((r) => setTimeout(r, SHORT_INTERVAL * 5))
    expect(fetcher).toHaveBeenCalledTimes(callCountBeforeUnmount)
  })
})
