/** 基础 UI 件：卡片、标题、统计块、标签、进度条。全项目共用，保证视觉一致。 */
import React from 'react'

export function Card({ title, extra, children, className = '', bodyClass = 'p-3' }) {
  return (
    <section className={`card ${className}`}>
      {(title || extra) && (
        <header className="flex items-center justify-between gap-2 border-b border-ink-700/70 px-3 py-2">
          <h2 className="card-title">
            {title}
          </h2>
          {extra ? <div className="flex items-center gap-2">{extra}</div> : null}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, unit, color, hint, className = '' }) {
  return (
    <div className={`min-w-0 ${className}`} title={hint}>
      <div className="kv-label truncate">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-lg leading-tight font-semibold" style={{ color: color || '#e2e8f0' }}>
          {value}
        </span>
        {unit ? <span className="text-[11px] text-slate-500">{unit}</span> : null}
      </div>
    </div>
  )
}

export function Tag({ children, color = '#94a3b8', solid = false, title, className = '' }) {
  const style = solid
    ? { backgroundColor: color, color: '#080b12', borderColor: color }
    : { color, backgroundColor: `${color}1f`, borderColor: `${color}66` }
  return (
    <span className={`chip ${className}`} style={style} title={title}>
      {children}
    </span>
  )
}

export function Bar({ value, max, color = '#22d3ee', height = 6, className = '' }) {
  const pct = max > 0 ? Math.min(100, (Number(value) / Number(max)) * 100) : 0
  return (
    <div
      className={`w-full overflow-hidden rounded-full bg-ink-700/70 ${className}`}
      style={{ height }}
      role="progressbar"
      aria-valuenow={Number(value) || 0}
      aria-valuemin={0}
      aria-valuemax={Number(max) || 0}
    >
      <div
        className="h-full rounded-full transition-[width] duration-300 ease-out"
        style={{ width: `${Math.max(pct, value > 0 ? 2 : 0)}%`, backgroundColor: color }}
      />
    </div>
  )
}

export function MetaRow({ label, children, mono = false }) {
  return (
    <div className="flex items-baseline gap-2 py-[3px]">
      <span className="kv-label w-20 shrink-0">{label}</span>
      <span className={`min-w-0 flex-1 text-[13px] text-slate-300 ${mono ? 'font-mono' : ''}`}>{children}</span>
    </div>
  )
}

export function Empty({ children = '暂无数据' }) {
  return <div className="py-3 text-center text-xs text-slate-500">{children}</div>
}

export function List({ items, ordered = false, className = '', itemClass = '' }) {
  if (!items?.length) return <Empty />
  return (
    <ol className={`space-y-1 ${className}`}>
      {items.map((it, i) => (
        <li key={i} className={`flex gap-2 text-[13px] leading-relaxed text-slate-300 ${itemClass}`}>
          <span className="mt-[3px] shrink-0 font-mono text-[11px] text-slate-500">
            {ordered ? `${String(i + 1).padStart(2, '0')}` : '·'}
          </span>
          <span className="min-w-0 flex-1">{it}</span>
        </li>
      ))}
    </ol>
  )
}

export function Spinner({ label = '加载中…' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-cyan-400/30 border-t-cyan-300" />
      {label}
    </div>
  )
}

export function ErrorBlock({ error, onRetry }) {
  return (
    <div className="card m-4 border-rose-400/40 bg-rose-500/5 p-5">
      <div className="mb-1 text-sm font-semibold text-rose-300">数据加载失败</div>
      <div className="mb-3 font-mono text-xs text-rose-200/80">{String(error?.message || error)}</div>
      <div className="mb-3 text-xs text-slate-400">
        mock 数据缺失时可运行 <code className="rounded bg-ink-800 px-1 py-0.5 text-slate-300">python3 web/scripts/export_mock.py</code> 重新生成；
        连真实后端请检查 <code className="rounded bg-ink-800 px-1 py-0.5 text-slate-300">VITE_API_BASE</code> 与 FastAPI 是否已启动。
      </div>
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  )
}
