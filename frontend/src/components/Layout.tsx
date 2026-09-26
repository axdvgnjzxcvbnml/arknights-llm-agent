import { NavLink, Outlet } from "react-router"
import {
  LayoutDashboard, Radio, History, BookOpen, Search, Network, User,
  LineChart, Gem, Cpu,
} from "lucide-react"
import type { ReactNode } from "react"
import { USE_MOCK } from "@/api/client"
import { fetchHealth } from "@/api/endpoints"
import { usePolling } from "@/lib/hooks"
import { cn } from "@/lib/utils"

function NavItem({ to, icon, label, end }: { to: string; icon: ReactNode; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
          isActive
            ? "bg-white/10 text-[hsl(var(--primary))]"
            : "text-slate-300 hover:bg-white/5",
        )
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  )
}

function TopBar() {
  const { data: health } = usePolling(fetchHealth, 5000)
  const vram = health?.vram
  const onlineCount = health ? Object.values(health.modules).filter((m) => m.online).length : 0
  const moduleCount = health ? Object.keys(health.modules).length : 0

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))] px-4">
      <div className="flex items-center gap-3">
        <span className="text-base font-semibold">arknights-llm-agent</span>
        <span className="rounded-sm border border-[hsl(var(--border))] px-1.5 py-0.5 text-[11px] uppercase text-slate-400">
          {health?.env ?? "…"}
        </span>
      </div>
      <div className="flex items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <Cpu className="h-3.5 w-3.5" />
          模块 {onlineCount}/{moduleCount}
        </span>
        <span title="显存占用（无 GPU / mock 时为 N/A）">
          显存{" "}
          {vram && vram.usedMb !== null && vram.totalMb !== null
            ? `${(vram.usedMb / 1024).toFixed(1)}/${(vram.totalMb / 1024).toFixed(1)}GB`
            : "N/A"}
        </span>
        {USE_MOCK ? (
          <span className="rounded-sm border border-dashed border-slate-400/50 px-1.5 py-0.5 text-slate-300">
            USE_MOCK
          </span>
        ) : null}
        <span className="hidden text-slate-500 sm:inline">{health?.serverVersion ?? ""}</span>
      </div>
    </header>
  )
}

export function Layout() {
  return (
    <div className="flex h-screen flex-col">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <nav className="flex w-52 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-[hsl(var(--border))] p-2">
          <NavItem to="/" end icon={<LayoutDashboard className="h-4 w-4" />} label="总览" />
          <NavItem to="/live" icon={<Radio className="h-4 w-4" />} label="实时对局" />
          <NavItem to="/replay" icon={<History className="h-4 w-4" />} label="对局回放" />

          <p className="px-3 pb-1 pt-4 text-[11px] uppercase tracking-wide text-slate-500">知识库</p>
          <NavItem to="/kb/rag" icon={<Search className="h-4 w-4" />} label="RAG 检索" />
          <NavItem to="/kb/graph" icon={<Network className="h-4 w-4" />} label="知识图谱" />
          <NavItem to="/kb/operator" icon={<User className="h-4 w-4" />} label="干员详情" />

          <p className="px-3 pb-1 pt-4 text-[11px] uppercase tracking-wide text-slate-500">运行</p>
          <NavItem to="/training" icon={<LineChart className="h-4 w-4" />} label="训练监控" />
          <NavItem to="/resources" icon={<Gem className="h-4 w-4" />} label="资源管理" />

          <p className="mt-auto flex items-center gap-1.5 px-3 pt-4 text-[11px] text-slate-600">
            <BookOpen className="h-3 w-3" /> 控制台骨架 · 待并入 web / web-kb
          </p>
        </nav>
        <main className="min-w-0 flex-1 overflow-y-auto p-4">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
