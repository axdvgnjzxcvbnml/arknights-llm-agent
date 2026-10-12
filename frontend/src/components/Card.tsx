import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export function Card({
  title,
  extra,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode
  extra?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section
      className={cn(
        "rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-sm",
        className,
      )}
    >
      {title ? (
        <header className="flex items-center justify-between gap-2 border-b border-[hsl(var(--border))] px-4 py-2.5">
          <h2 className="text-sm font-semibold text-[hsl(var(--card-foreground))]">{title}</h2>
          {extra}
        </header>
      ) : null}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  )
}

/**
 * 错误/降级态：后端 503、404 或超时时用。
 * 与 EmptyState 的区别是它明确告知"数据取不到"而不是"暂时没有数据"，
 * 避免像之前那样在 503 时永远停在"加载中…"。
 */
export function ErrorState({ text, hint, detail }: { text: string; hint?: string; detail?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-md border border-dashed border-rose-400/40 bg-rose-500/5 py-8 text-center">
      <p className="text-sm text-rose-200">{text}</p>
      {hint ? <p className="text-xs text-slate-400">{hint}</p> : null}
      {detail ? <p className="max-w-md font-mono text-[11px] text-slate-500">{detail}</p> : null}
    </div>
  )
}

export function EmptyState({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-md border border-dashed border-[hsl(var(--border))] py-8 text-center">
      <p className="text-sm text-slate-400">{text}</p>
      {hint ? <p className="text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}
