# 前端合并方案（frontend_merge_plan）

> 本文是 **执行手册**，等 Qwen 的 `web/` 到齐后直接照着做。不执行合并，只写方案。
> 合并目标：`frontend/`（统一外壳，已有）+ `web/`（Qwen 对局回放）+ `web-kb/`（Kimi 知识库三页）
> → 统一 `frontend/`。合并后删除 `web/` 和 `web-kb/` 两个独立工程。

---

## 一、合并目标与原则

| 原则 | 说明 |
|------|------|
| **以 frontend/ 为基础** | 已有统一外壳（BrowserRouter + Layout + 6 模块 Dashboard），路由结构已预留 /replay 和 /kb/* 占位 |
| **页面移植，不重写** | web/ 的 Replay 页、web-kb 的三页直接移植，只改 import 路径和 API 调用层，不改业务逻辑 |
| **API 层统一** | 三份 client（frontend/client.ts + endpoints.ts、web-kb/client.ts、web/api.js）合并为一份 |
| **类型统一为 camelCase** | frontend 已用 deepCamelize，web-kb 的 snake_case 类型在移植时转换 |
| **组件按需引入** | web-kb 的 70+ shadcn/ui 组件不全部搬，只搬页面实际用到的（约 10–15 个） |
| **mock 数据合并** | 三份 public/mock/ 合并到 frontend/public/mock/，文件名不冲突 |
| **保留 git 历史** | 用 `git mv` / 复制保留文件来源，合并后 web/ 和 web-kb/ 目录删除 |

---

## 二、路由映射（合并后 frontend/src/App.tsx）

```
/                    → Dashboard（已有，6 模块）
/live                → Live（已有，实时对局占位→Qwen web/ 合并后替换）
/replay              → Replay（Qwen web/ 的对局回放页，替换占位）
/resources           → Resources（已有，资源仪表盘）
/training            → Training（已有，训练进度）
/kb                  → 重定向到 /kb/rag
/kb/rag              → RagPage（web-kb 移植，替换 KbRag 占位）
/kb/graph            → GraphPage（web-kb 移植，替换 KbGraph 占位）
/kb/operator         → OperatorPage（web-kb 移植，替换 KbOperator 占位）
```

> web-kb 当前路由是 `/rag` `/graph` `/operator`（无 /kb 前缀），移植后加 `/kb` 前缀。
> web/ 当前路由是 `/replay`，与 frontend 已预留的 `/replay` 一致，直接替换占位。

---

## 三、公共代码抽取

### 3.1 API 客户端合并（三份 → 一份）

| 来源 | 当前文件 | 合并后位置 | 处理方式 |
|------|----------|-----------|----------|
| frontend | `src/api/client.ts` + `src/api/endpoints.ts` | `frontend/src/api/client.ts` + `endpoints.ts` | **保留为基础**，已有 USE_MOCK 切换、deepCamelize、fetchJson 封装 |
| web-kb | `src/api/client.ts` | `frontend/src/api/endpoints.ts` | 知识库 API 函数（getOperatorDetail/searchRag/getGraphSubgraph/getRecommend 等）**追加到 endpoints.ts**，改用 frontend 的 fetchJson + deepCamelize |
| web | `src/api.js`（JS） | `frontend/src/api/endpoints.ts` | 对局日志 API（getEpisode/getEpisodeSteps）转为 TS 追加到 endpoints.ts |

**合并后 endpoints.ts 的函数分组**：
```
// Dashboard 9 接口（已有）
fetchHealth / fetchLiveSnapshot / fetchSourceStone / fetchAccount / fetchProgress /
fetchTasks / fetchTrainingRuns / fetchTrainingMetrics

// 知识库工具（web-kb 移植）
fetchOperator / fetchSkill / fetchEnemy / fetchStage / searchGuide / fetchRecommend

// 知识图谱（web-kb 移植）
fetchGraphOverview / fetchGraphNode / fetchGraphSubgraph

// 对局日志（web/ 移植）
fetchEpisode / fetchEpisodeSteps / fetchEpisodes（列表）
```

**关键改动**：web-kb 的 client.ts 直接用 snake_case 类型（无 deepCamelize），移植后必须：
1. 调用 frontend 的 `getApi<T>(path)`（内部已 deepCamelize）
2. 类型从 `types/kb.ts`（snake_case）转换为 `types/index.ts`（camelCase），或在 kb.ts 里直接写 camelCase 类型

### 3.2 Evidence 分级渲染组件（统一到 frontend）

| 来源 | 当前实现 | 合并后 |
|------|----------|--------|
| frontend | `src/components/EvidenceBadge.tsx`（7 色：fact/retrieved/inferred/estimated/cv/vlm/mock，retrieved/inferred/estimated 虚线边框）+ `EvidenceList` | **保留为唯一实现** |
| web-kb | 无独立组件，页面内联渲染 evidence（用 shadcn Badge） | 页面移植时改用 `EvidenceBadge` / `EvidenceList` |
| web | 有自己的 evidence 渲染组件 | 废弃，改用 frontend 的 `EvidenceBadge` |

**注意**：web-kb 的 `EvidenceLevel` 类型只有 `fact | retrieved | inferred` 三档，frontend 有 7 档。
合并后统一用 frontend 的 7 档类型，web-kb 页面里的 evidence 数据如果只有三档，自动兼容（7 档是超集）。

### 3.3 工具函数合并

| 函数 | frontend | web-kb | web | 合并后 |
|------|----------|--------|-----|--------|
| `cn`（className 合并） | `lib/utils.ts` | `lib/utils.ts` | 有 | 保留 frontend 的 |
| `deepCamelize`（snake→camel） | `lib/utils.ts` | 无 | 无 | 保留 frontend 的（web-kb 移植后需要） |
| `formatDuration` / `formatDate` | `lib/utils.ts` | 无 | 有 | 合并到 frontend 的 `lib/utils.ts` |
| `use-mobile` hook | 无 | `hooks/use-mobile.ts` | 无 | 移植到 `frontend/src/lib/hooks.ts`（如 shadcn 组件需要） |

### 3.4 类型定义合并

| 文件 | 内容 | 处理 |
|------|------|------|
| `frontend/src/types/index.ts` | Dashboard 类型 + Evidence/EvidenceLevel + 通用类型 | **保留为基础** |
| `web-kb/src/types/kb.ts` | 知识库类型（OperatorDetail/SkillBrief/TraitInfo/RagHit/SubgraphResponse 等） | 移植到 `frontend/src/types/kb.ts`，**字段名改为 camelCase**（因为 API 层统一 deepCamelize） |
| `web/` 的类型 | 对局日志类型（Episode/StepRecord/Reward 等） | 移植到 `frontend/src/types/episode.ts`，camelCase |

---

## 四、合并步骤（逐文件）

### Phase 0：准备（web/ 到齐后）

1. 确认 `web/` 的技术栈（React 版本、Vite 版本、Tailwind 版本、路由库）与 frontend 一致
2. 确认 `web/` 的目录结构和关键文件（App.tsx / main.tsx / api.js / 页面组件 / 类型）
3. 跑 `cd frontend && npm run build` 确认当前 frontend 构建通过（基线）
4. 跑 `cd web && npm install && npm run build` 确认 web/ 构建通过
5. 跑 `cd web-kb && npm run build` 确认 web-kb 构建通过

### Phase 1：移植 web-kb 知识库三页（不依赖 web/，可先做）

**直接复制（不改内容）**：
```
web-kb/src/pages/RagPage.tsx        → frontend/src/pages/kb/RagPage.tsx
web-kb/src/pages/GraphPage.tsx      → frontend/src/pages/kb/GraphPage.tsx
web-kb/src/pages/OperatorPage.tsx   → frontend/src/pages/kb/OperatorPage.tsx
```

**需要改写 import 路径**（三个页面文件内）：
- `@/types/kb` → `@/types/kb`（路径不变，但文件内容需改 camelCase）
- `@/api/client` → `@/api/client`（路径不变，但函数签名变了）
- `@/components/ui/*` → `@/components/ui/*`（需先搬用到的 shadcn 组件）
- `@/lib/utils` → `@/lib/utils`（路径不变）
- `@/components/Layout` → 删除（页面不再自己包 Layout，由 App.tsx 的路由统一包）

**需要搬的 shadcn/ui 组件**（先 grep 三个页面的 import，只搬用到的）：
```
# 预计用到的（需实际 grep 确认）
web-kb/src/components/ui/card.tsx         → frontend/src/components/ui/card.tsx
web-kb/src/components/ui/input.tsx        → frontend/src/components/ui/input.tsx
web-kb/src/components/ui/button.tsx       → frontend/src/components/ui/button.tsx
web-kb/src/components/ui/select.tsx       → frontend/src/components/ui/select.tsx
web-kb/src/components/ui/table.tsx        → frontend/src/components/ui/table.tsx
web-kb/src/components/ui/tabs.tsx         → frontend/src/components/ui/tabs.tsx
web-kb/src/components/ui/badge.tsx        → frontend/src/components/ui/badge.tsx
web-kb/src/components/ui/accordion.tsx    → frontend/src/components/ui/accordion.tsx
web-kb/src/components/ui/scroll-area.tsx  → frontend/src/components/ui/scroll-area.tsx
web-kb/src/components/ui/skeleton.tsx     → frontend/src/components/ui/skeleton.tsx
```
> 实际清单以 `grep "from '@/components/ui" web-kb/src/pages/*.tsx` 为准，不臆造。

**需要合并的文件**：
- `web-kb/src/api/client.ts` 的知识库 API 函数 → 追加到 `frontend/src/api/endpoints.ts`
- `web-kb/src/types/kb.ts` → 复制到 `frontend/src/types/kb.ts`，字段名改 camelCase
- `web-kb/public/mock/*.json` → 复制到 `frontend/public/mock/`（检查文件名冲突：web-kb 有 operator_*.json / graph_*.json / rag_*.json / catalog.json，frontend 有 health/live/source-stone/account/progress/tasks/training-*.json，**无冲突**）

**需要删除的文件**（web-kb 工程入口，合并后不需要）：
```
web-kb/src/App.tsx          # 路由由 frontend App.tsx 统一
web-kb/src/main.tsx         # 入口由 frontend main.tsx 统一
web-kb/src/components/Layout.tsx  # Layout 由 frontend 统一
web-kb/src/index.css        # 样式由 frontend 统一（需检查 tailwind 配置是否一致）
```

**改 App.tsx**：把 `/kb/*` 的三个占位（KbRag/KbGraph/KbOperator）替换为移植后的真实页面。

### Phase 2：移植 web/ 对局回放页（web/ 到齐后）

**直接复制**：
```
web/src/pages/Replay.tsx（或对应文件名）  → frontend/src/pages/Replay.tsx（替换占位）
web/src/components/（对局回放用到的子组件） → frontend/src/components/replay/
```

**需要改写**：
- `web/src/api.js` → 转为 TS，对局日志 API 函数追加到 `frontend/src/api/endpoints.ts`
- web/ 的类型 → 复制到 `frontend/src/types/episode.ts`，camelCase
- web/ 的 evidence 渲染组件 → 改用 `frontend/src/components/EvidenceBadge.tsx`
- web/ 的 mock 数据 → 复制到 `frontend/public/mock/`（检查文件名冲突）

**需要删除**：
```
web/src/App.tsx / main.tsx / index.css  # 入口由 frontend 统一
```

### Phase 3：统一配置与清理

1. **package.json**：合并依赖（shadcn 相关依赖、recharts、lucide-react 等），跑 `npm install`
2. **tailwind.config.js**：确认 frontend 的配置包含 web-kb/web 用到的自定义颜色/动画
3. **vite.config.ts**：确认 proxy 配置（/api + /ws），端口 3001
4. **tsconfig.json**：确认路径别名 `@/*` 指向 `src/*`
5. **删除 web/ 和 web-kb/ 目录**（确认所有文件已移植后）
6. **更新 frontend/README.md**：合并后的功能清单、路由表、构建命令

### Phase 4：验证

1. `cd frontend && npm run build` 构建通过
2. `VITE_USE_MOCK=true npm run dev`：所有路由可访问，mock 数据正常渲染
3. `VITE_USE_MOCK=false npm run dev` + FastAPI：所有页面能拉到真实后端数据
4. 截图保存到 `docs/screenshots/`（Dashboard / Replay / KB-RAG / KB-Graph / KB-Operator 各一张）
5. 跑后端全量 pytest，确认前端合并不影响后端

---

## 五、冲突预案

### 5.1 已知冲突点

| 冲突点 | 详情 | 解决方案 |
|--------|------|----------|
| **API client 三份** | frontend（TS + deepCamelize）、web-kb（TS + snake_case）、web（JS） | 以 frontend 为基础，web-kb/web 的 API 函数追加到 endpoints.ts，统一用 deepCamelize |
| **类型命名风格** | frontend camelCase、web-kb snake_case | 统一为 camelCase；web-kb 的 kb.ts 移植时字段名改写 |
| **Evidence 组件** | frontend 有 7 色 EvidenceBadge、web-kb 内联渲染、web 有自己的 | 统一用 frontend 的 EvidenceBadge；web-kb/web 页面移植时替换 |
| **EvidenceLevel 类型范围** | frontend 7 档、web-kb 3 档（fact/retrieved/inferred） | 统一用 frontend 的 7 档（超集兼容）；web-kb 数据自动兼容 |
| **shadcn/ui 组件** | web-kb 有 70+ 个、frontend 只有自定义组件 | 只搬页面实际用到的（grep 确认），不全部搬 |
| **Layout 组件** | frontend 和 web-kb 各有一份 Layout | 统一用 frontend 的 Layout；web-kb 页面不再自己包 Layout |
| **index.css / tailwind 配置** | 三份工程各有一份 | 统一用 frontend 的；检查 web-kb/web 用到的自定义 CSS 是否需要合并 |
| **package.json 依赖版本** | 三份工程的依赖版本可能不同 | 以 frontend 的版本为基准，合并时取较高版本；recharts/lucide-react/shadcn 依赖需确认 |
| **mock 数据文件名** | 三份 public/mock/ 可能有同名文件 | 目前检查无冲突；合并时逐一确认，冲突则重命名加前缀 |

### 5.2 web-kb 克制规则（R1/R2/R3）处理

web-kb 早期版本曾在前端本地复刻知识图谱的克制规则（R1/R2/R3），第十三批已改为
**方案 A：前端只消费后端 API**（`/api/graph/subgraph/{stage_id}` + `/api/recommend/{stage_id}`），
不再本地建图/复刻规则。

合并时确认：
- [ ] web-kb 的 `RagPage` / `GraphPage` / `OperatorPage` 不包含本地建图逻辑（`buildGraph` / `deriveCounterRules` 等）
- [ ] 所有克制/推荐数据来自后端 API（`fetchRecommend` / `fetchGraphSubgraph`）
- [ ] `web-kb/AUDIT.md` 的 C1–C6 修复状态已全部标注为"已消除"
- [ ] evidence 分级：COUNTERS / RECOMMENDS 边的 evidence 为 `inferred`，前端用虚线边框渲染

### 5.3 web/ 未知冲突（等 web/ 到齐后确认）

- [ ] web/ 的技术栈版本是否与 frontend 一致（React 19 / Vite 7 / Tailwind 3.4 / RR 7）
- [ ] web/ 是否用了不同的 CSS 方案（CSS Modules / styled-components 等）
- [ ] web/ 的对局回放页是否依赖特定的图表库（recharts / chart.js 等）
- [ ] web/ 的 API 调用是否用了不同的 fetch 封装（axios / react-query 等）

---

## 六、验收清单

### 6.1 构建与路由

- [ ] `cd frontend && npm run build` 构建通过，无 TS 错误
- [ ] `npm run dev` 启动后，以下路由均可访问且不白屏：
  - `/`（Dashboard）
  - `/live`（实时对局）
  - `/replay`（对局回放，web/ 移植）
  - `/resources`（资源仪表盘）
  - `/training`（训练进度）
  - `/kb/rag`（RAG 检索，web-kb 移植）
  - `/kb/graph`（知识图谱，web-kb 移植）
  - `/kb/operator`（干员详情，web-kb 移植）
- [ ] 导航栏/侧边栏的链接全部正确，无 404

### 6.2 数据联调

- [ ] `VITE_USE_MOCK=true`：所有页面用 mock 数据正常渲染，无控制台报错
- [ ] `VITE_USE_MOCK=false` + FastAPI（`python -m api.server`）：
  - Dashboard 6 模块全部拉到真实数据（health/live/source-stone/account/progress/tasks/training）
  - `/replay` 能拉到对局日志（`/api/episode/{id}` + `/api/episode/{id}/steps`）
  - `/kb/rag` 能搜索到 RAG 结果（`/api/search?q=xxx`）
  - `/kb/graph` 能显示图谱（`/api/graph/overview` + `/api/graph/subgraph/3-8`）
  - `/kb/operator` 能显示干员详情（`/api/operator/能天使`）
- [ ] WebSocket `/ws/live` 连接正常，实时对局卡片能收到帧推送

### 6.3 可解释性

- [ ] 所有页面的 evidence 分级渲染统一用 `EvidenceBadge`（7 色）
- [ ] `retrieved` / `inferred` / `estimated` 三档用虚线边框
- [ ] 对局回放页的每步决策显示 reasoning + knowledge_used + evidence 分级
- [ ] 知识图谱页的 COUNTERS / RECOMMENDS 边标注 `inferred`

### 6.4 清理与文档

- [ ] `web/` 和 `web-kb/` 目录已删除（确认所有文件已移植后）
- [ ] `frontend/package.json` 依赖已合并，`node_modules` 重新安装
- [ ] `frontend/README.md` 已更新（合并后的功能清单、路由表、构建命令）
- [ ] 截图保存到 `docs/screenshots/`（至少 5 张：Dashboard / Replay / KB-RAG / KB-Graph / KB-Operator）
- [ ] 后端全量 pytest 通过（前端合并不影响后端）
- [ ] `bash scripts/run_smoke.sh` 四段全绿

### 6.5 提交

- [ ] 合并改动分 commit 提交（Phase 1 / Phase 2 / Phase 3 分开）
- [ ] commit message 标注 `feat(frontend): 合并 web-kb 知识库三页` / `feat(frontend): 合并 web/ 对局回放页`
- [ ] 不推送（等用户确认后统一推送）

---

## 七、合并后目录结构（目标态）

```
frontend/
├── public/
│   └── mock/                    # 合并后的 mock 数据（frontend + web-kb + web）
│       ├── health.json
│       ├── live.json
│       ├── source-stone.json
│       ├── account.json
│       ├── progress.json
│       ├── tasks.json
│       ├── training-runs.json
│       ├── training-metrics.json
│       ├── catalog.json          # web-kb
│       ├── operator_*.json       # web-kb
│       ├── graph_*.json          # web-kb
│       ├── rag_*.json            # web-kb
│       └── episode_*.json        # web
├── src/
│   ├── api/
│   │   ├── client.ts             # 统一 API 客户端（USE_MOCK + deepCamelize）
│   │   └── endpoints.ts          # 所有 API 函数（Dashboard + 知识库 + 图谱 + 对局日志）
│   ├── components/
│   │   ├── Card.tsx
│   │   ├── EvidenceBadge.tsx     # 统一 7 色 evidence 渲染
│   │   ├── Layout.tsx            # 统一布局
│   │   ├── Placeholder.tsx
│   │   ├── ui/                   # shadcn 组件（只搬用到的，约 10–15 个）
│   │   │   ├── card.tsx
│   │   │   ├── input.tsx
│   │   │   ├── button.tsx
│   │   │   └── ...
│   │   └── replay/               # web/ 对局回放的子组件
│   ├── pages/
│   │   ├── Dashboard.tsx         # 已有
│   │   ├── Live.tsx              # 已有
│   │   ├── Replay.tsx            # web/ 移植（替换占位）
│   │   ├── Resources.tsx         # 已有
│   │   ├── Training.tsx          # 已有
│   │   ├── dashboard/            # Dashboard 6 卡片（已有）
│   │   └── kb/                   # web-kb 移植（替换占位）
│   │       ├── RagPage.tsx
│   │       ├── GraphPage.tsx
│   │       └── OperatorPage.tsx
│   ├── types/
│   │   ├── index.ts              # Dashboard + 通用类型
│   │   ├── kb.ts                 # 知识库类型（camelCase，从 web-kb 移植）
│   │   └── episode.ts            # 对局日志类型（camelCase，从 web/ 移植）
│   ├── lib/
│   │   ├── utils.ts              # cn + deepCamelize + formatDuration + formatDate
│   │   └── hooks.ts              # 自定义 hooks（含 use-mobile）
│   ├── App.tsx                   # 统一路由（BrowserRouter + 8 条路由）
│   ├── main.tsx
│   ├── index.css
│   └── vite-env.d.ts
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
└── README.md
```
