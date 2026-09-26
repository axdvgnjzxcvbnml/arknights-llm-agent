import { Link, NavLink } from 'react-router';
import { Search, Share2, UserRound } from 'lucide-react';
import type { ReactNode } from 'react';

const NAV = [
  { to: '/rag', icon: Search, label: 'RAG 检索', desc: 'Top-K 相似度检索' },
  { to: '/graph', icon: Share2, label: '知识图谱', desc: '实体关系网络' },
  { to: '/operator', icon: UserRound, label: '干员详情', desc: '档案与关联' },
];

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link to="/" className="flex items-baseline gap-2 shrink-0">
            <span className="text-base font-bold tracking-wide">
              ARKNIGHTS<span className="text-primary">·KB</span>
            </span>
            <span className="hidden text-xs text-muted-foreground sm:inline">知识库浏览器</span>
          </Link>
          <nav className="flex items-center gap-1">
            {NAV.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-secondary text-primary font-medium'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60'
                  }`
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>
          <span className="ml-auto rounded border border-primary/40 bg-primary/10 px-2 py-0.5 font-mono-num text-[11px] text-primary">
            MOCK · prts_raw
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      <footer className="border-t border-border py-4 text-center text-xs text-muted-foreground">
        arknights-llm-agent · web-kb — 数据为本地 mock，API 上线后切换至 /api/*
      </footer>
    </div>
  );
}
