import { Link } from "react-router"
import { Radio, History, Search, Network, User, type LucideIcon } from "lucide-react"
import { Card } from "@/components/Card"

const LINKS: { to: string; label: string; desc: string; icon: LucideIcon }[] = [
  { to: "/live", label: "实时对局", desc: "截图 / 状态 / 决策流", icon: Radio },
  { to: "/replay", label: "对局回放", desc: "逐步 reasoning 与奖励", icon: History },
  { to: "/kb/rag", label: "RAG 检索", desc: "PRTS 知识检索", icon: Search },
  { to: "/kb/graph", label: "知识图谱", desc: "干员/敌人/关卡关系", icon: Network },
  { to: "/kb/operator", label: "干员详情", desc: "干员 / 技能 / 特性", icon: User },
]

export function QuickLinksCard() {
  return (
    <Card title="快捷入口">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {LINKS.map(({ to, label, desc, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className="group rounded-md border border-[hsl(var(--border))] bg-white/[0.02] p-3 transition-colors hover:border-[hsl(var(--primary))]/50 hover:bg-white/5"
          >
            <Icon className="mb-1.5 h-4 w-4 text-[hsl(var(--primary))]" />
            <p className="text-sm font-medium text-slate-100 group-hover:text-white">{label}</p>
            <p className="text-[11px] text-slate-500">{desc}</p>
          </Link>
        ))}
      </div>
    </Card>
  )
}
