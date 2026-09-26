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

export function EmptyState({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-md border border-dashed border-[hsl(var(--border))] py-8 text-center">
      <p className="text-sm text-slate-400">{text}</p>
      {hint ? <p className="text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}
