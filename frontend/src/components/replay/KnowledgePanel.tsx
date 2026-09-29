// @ts-nocheck
import React from 'react'
import { Card, Empty } from '@/components/replay/ui'
import EvidenceBadge from './EvidenceBadge.jsx'

/**
 * 检索知识（RAG + 知识图谱）：每条引用带 evidence 分级、doc_type、相似度。
 * 界面上明确区分"事实"与"参考/推断"，避免把 retrieved 当结论用。
 */
export default function KnowledgePanel({ step }) {
  const k = step.knowledge || {}
  const cites = k.citations || []

  return (
    <Card
      title="检索知识 · RAG / 图谱"
      extra={<span className="font-mono text-[11px] text-slate-500">{cites.length} 条引用</span>}
    >
      {k.query ? (
        <div className="mb-2 flex items-start gap-2 rounded-md border border-ink-700/70 bg-ink-850/60 px-2 py-1.5">
          <span className="kv-label shrink-0 pt-px">检索式</span>
          <span className="min-w-0 flex-1 text-[12px] text-slate-300">{k.query}</span>
        </div>
      ) : null}

      {cites.length ? (
        <ul className="space-y-1.5">
          {cites.map((c, i) => (
            <li key={i} className="rounded-md border border-ink-700/70 bg-ink-850/50 px-2.5 py-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <EvidenceBadge level={c.evidence} showCn />
                <span className="text-[12px] font-medium text-slate-200">{c.source || '—'}</span>
                {c.docType ? <span className="chip border-ink-600 bg-ink-800 font-mono text-[10px] text-slate-500">{c.docType}</span> : null}
                {c.score !== null && c.score !== undefined ? (
                  <span className="ml-auto font-mono text-[10px] text-slate-500" title="RAG 相似度">
                    score {Number(c.score).toFixed(3)}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-[12px] leading-relaxed text-slate-300">{c.detail}</p>
              {c.url ? (
                <a
                  href={c.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-1 block truncate font-mono text-[10px] text-cyan-400/70 hover:text-cyan-300"
                >
                  {c.url}
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <Empty>本步未引用外部知识</Empty>
      )}

      {k.contextText ? (
        <details className="mt-2 border-t border-ink-700/70 pt-2">
          <summary className="cursor-pointer text-[11px] text-slate-500 hover:text-slate-300">
            拼给 LLM 的上下文原文（context_text）
          </summary>
          <pre className="scrollbar-thin mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-ink-700/70 bg-ink-950/70 p-2 font-mono text-[11px] leading-relaxed text-slate-400">
            {k.contextText}
          </pre>
        </details>
      ) : null}
    </Card>
  )
}
