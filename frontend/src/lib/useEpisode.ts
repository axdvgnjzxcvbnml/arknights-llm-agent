import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchEpisodeFull, listEpisodes } from '@/api/episode'
import type { EpisodeFull, EpisodeIndex, StepDto } from '@/types/episode'

/** 异步加载状态：loading / error / data 三态 */
export interface AsyncState<T> {
  loading: boolean
  error: unknown
  data: T | null
}

/**
 * 对局数据加载：列表 + 单局完整数据（报告 + 每步详情）。
 * 切换对局时带竞态保护（只接受最后一次请求的结果）。
 */
export function useEpisode() {
  const [index, setIndex] = useState<AsyncState<EpisodeIndex>>({ loading: true, error: null, data: null })
  const [episodeId, setEpisodeId] = useState<string | null>(null)
  const [doc, setDoc] = useState<AsyncState<EpisodeFull>>({ loading: false, error: null, data: null })

  const loadIndex = useCallback(async () => {
    setIndex((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await listEpisodes()
      setIndex({ loading: false, error: null, data })
      return data
    } catch (err) {
      setIndex({ loading: false, error: err, data: null })
      return null
    }
  }, [])

  const loadEpisode = useCallback(async (id: string) => {
    if (!id) return
    setDoc({ loading: true, error: null, data: null })
    try {
      const data = await fetchEpisodeFull(id)
      setDoc({ loading: false, error: null, data })
    } catch (err) {
      setDoc({ loading: false, error: err, data: null })
    }
  }, [])

  // 首次进入：拉列表并默认选中第一局
  useEffect(() => {
    let alive = true
    ;(async () => {
      const data = await loadIndex()
      const first = data?.episodes?.[0]?.id
      if (alive && first) setEpisodeId(first)
    })()
    return () => {
      alive = false
    }
  }, [loadIndex])

  // 选中的对局变化 -> 拉完整数据（带竞态保护）
  useEffect(() => {
    if (!episodeId) return
    let alive = true
    setDoc({ loading: true, error: null, data: null })
    fetchEpisodeFull(episodeId)
      .then((data) => {
        if (alive) setDoc({ loading: false, error: null, data })
      })
      .catch((err) => {
        if (alive) setDoc({ loading: false, error: err, data: null })
      })
    return () => {
      alive = false
    }
  }, [episodeId])

  const retry = useCallback(() => {
    if (index.error) loadIndex()
    if (episodeId) loadEpisode(episodeId)
  }, [index.error, episodeId, loadIndex, loadEpisode])

  const steps: StepDto[] = useMemo(() => doc.data?.steps ?? [], [doc.data])

  return {
    index,
    episodes: index.data?.episodes || [],
    generatedAt: index.data?.generatedAt || '',
    episodeId,
    selectEpisode: setEpisodeId,
    doc,
    episode: doc.data?.episode || null,
    steps,
    retry,
  }
}
