// @ts-nocheck
import React, { useEffect, useState } from 'react'
import { fetchRawLogs } from '@/api/episode'
import { Spinner } from '@/components/replay/ui'

/**
 * 原始日志抽屉：直接展示 results/*.txt 的同源文本（由 export_mock.py 一并导出），
 * 方便把可视化结果和原始报告逐行对照 —— 复盘时很有用。
 */
export default function RawLogDrawer({ open, onClose }) {
  const [logs, setLogs] = useState(null)
  const [error, setError] = useState(null)
  const [activeId, setActiveId] = useState(null)

  useEffect(() => {
    if (!open || logs) return
    let alive = true
    fetchRawLogs()
      .then((data) => {
        if (!alive) return
        const list = Array.isArray(data) ? data : data?.logs || []
        setLogs(list)
        setActiveId(list[0]?.id || null)
      })
      .catch((err) => alive && setError(err))
    return () => {
      alive = false
    }
  }, [open, logs])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  const active = (logs || []).find((l) => l.id === activeId) || null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-[2px]" onClick={onClose} role="dialog" aria-modal="true" aria-label="原始日志">
      <aside
        className="flex h-full w-full max-w-4xl flex-col border-l border-ink-700 bg-ink-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3 border-b border-ink-700 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-100">原始日志（results/*.txt 同源）</h2>
          <button type="button" className="btn ml-auto" onClick={onClose}>
            关闭 ✕
          </button>
        </header>

        <div className="flex flex-wrap gap-1.5 border-b border-ink-700/70 px-4 py-2">
          {(logs || []).map((l) => (
            <button
              key={l.id}
              type="button"
              className={`btn px-2 py-1 ${l.id === activeId ? 'btn-active' : ''}`}
              onClick={() => setActiveId(l.id)}
              title={l.path}
            >
              {l.title}
            </button>
          ))}
        </div>

        <div className="scrollbar-thin min-h-0 flex-1 overflow-auto p-4">
          {error ? (
            <div className="text-sm text-rose-300">加载失败：{String(error.message || error)}</div>
          ) : !active ? (
            <Spinner label="加载原始日志…" />
          ) : (
            <>
              <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                <span className="chip border-ink-600 bg-ink-800 font-mono">{active.path}</span>
                <span>由 {active.generatedBy} 生成</span>
                <button
                  type="button"
                  className="btn ml-auto px-2 py-0.5"
                  onClick={() => {
                    const blob = new Blob([active.text], { type: 'text/plain;charset=utf-8' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `${active.id}.txt`
                    a.click()
                    URL.revokeObjectURL(url)
                  }}
                >
                  下载 .txt
                </button>
              </div>
              <pre className="whitespace-pre-wrap rounded-md border border-ink-700/70 bg-ink-900/70 p-3 font-mono text-[11.5px] leading-relaxed text-slate-300">
                {active.text}
              </pre>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
