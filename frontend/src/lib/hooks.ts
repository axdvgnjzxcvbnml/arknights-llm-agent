import { useEffect, useRef, useState } from "react"

/** 定时轮询（实时对局/系统状态）。页面卸载时清理；WS 接入后仅替换这一层。 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      try {
        const d = await fetcher()
        if (alive.current) {
          setData(d)
          setError(null)
        }
      } catch (e) {
        if (alive.current) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (alive.current) setLoading(false)
        timer = setTimeout(tick, intervalMs)
      }
    }
    tick()
    return () => {
      alive.current = false
      clearTimeout(timer)
    }
    // fetcher 由各页面以稳定引用传入；轮询间隔变化即重建
  }, [fetcher, intervalMs])

  return { data, error, loading }
}
