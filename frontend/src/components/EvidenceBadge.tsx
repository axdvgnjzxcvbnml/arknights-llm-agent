import { cn } from "@/lib/utils"
import type { Evidence, EvidenceLevel } from "@/types"

/**
 * 证据分级标签（7 色）。这是从 web/web-kb 抽出的公共渲染逻辑，统一外壳先建好，
 * 后续两个前端合并时直接复用，避免各写一套导致分级漂移。
 *
 * retrieved / inferred / estimated 三档用**虚线边框**，提示"非确定事实"：
 * retrieved=检索到的外部观点，inferred=推断，estimated=估算；
 * fact/cv 实线（实测/确认），vlm/mock 用各自语义色。
 */

const STYLE: Record<EvidenceLevel, { text: string; bg: string; border: string; dashed?: boolean }> = {
  fact: { text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-400/40" },
  retrieved: { text: "text-sky-300", bg: "bg-sky-500/10", border: "border-sky-400/50", dashed: true },
  inferred: { text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-400/50", dashed: true },
  estimated: { text: "text-orange-300", bg: "bg-orange-500/10", border: "border-orange-400/50", dashed: true },
  cv: { text: "text-teal-300", bg: "bg-teal-500/10", border: "border-teal-400/40" },
  vlm: { text: "text-violet-300", bg: "bg-violet-500/10", border: "border-violet-400/40" },
  mock: { text: "text-slate-300", bg: "bg-slate-500/15", border: "border-slate-400/40" },
}

const LABEL: Record<EvidenceLevel, string> = {
  fact: "事实",
  retrieved: "检索",
  inferred: "推断",
  estimated: "估算",
  cv: "CV确认",
  vlm: "VLM观点",
  mock: "MOCK",
}

export function levelLabel(level: EvidenceLevel): string {
  return LABEL[level] ?? level
}

export function EvidenceBadge({ level, source, className }: Evidence & { className?: string }) {
  const s = STYLE[level] ?? STYLE.mock
  return (
    <span
      title={source}
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[11px] leading-none whitespace-nowrap",
        s.text, s.bg, s.border,
        s.dashed ? "border-dashed" : "border-solid",
        className,
      )}
    >
      <span className="font-medium">{LABEL[level] ?? level}</span>
      {source ? <span className="opacity-70">{source}</span> : null}
    </span>
  )
}

/** 一组证据标签。 */
export function EvidenceList({ items, className }: { items: Evidence[]; className?: string }) {
  if (!items.length) return <span className="text-xs text-slate-500">无引用</span>
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {items.map((e, i) => (
        <EvidenceBadge key={`${e.level}-${e.source}-${i}`} level={e.level} source={e.source} />
      ))}
    </div>
  )
}
