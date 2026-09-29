# arknights-llm-agent Frontend

统一前端：Dashboard + 对局回放 + 知识库浏览器。

## 技术栈

- React 19 + TypeScript 5.9
- Vite 7 + Tailwind CSS 3.4
- React Router 7
- Recharts（图表）
- shadcn/ui（知识库页面）
- d3（知识图谱力导向图）

## 路由

| 路径 | 页面 | 来源 |
|------|------|------|
| `/` | Dashboard 总览（6模块） | frontend 原生 |
| `/live` | 实时对局（占位） | frontend 原生 |
| `/replay` | 对局回放（可解释决策日志） | Qwen web/ 移植 |
| `/resources` | 资源仪表盘 | frontend 原生 |
| `/training` | 训练进度 | frontend 原生 |
| `/kb/rag` | RAG 检索 | Kimi web-kb/ 移植 |
| `/kb/graph` | 知识图谱 | Kimi web-kb/ 移植 |
| `/kb/operator` | 干员详情 | Kimi web-kb/ 移植 |

## 快速开始

```bash
cd frontend
npm install

# mock 模式（默认，不依赖后端）
npm run dev

# 连本地 FastAPI
VITE_USE_MOCK=false npm run dev

# 构建
npm run build

# 测试
npm test
```

## 目录结构

```
frontend/src/
├── api/
│   ├── client.ts          # 统一 API 客户端（USE_MOCK + deepCamelize）
│   ├── endpoints.ts       # Dashboard + 知识库 API
│   └── episode.ts         # 对局日志 API（web/ 移植，@ts-nocheck）
├── components/
│   ├── EvidenceBadge.tsx  # 统一 7 色 evidence 渲染
│   ├── Layout.tsx
│   ├── ui/                # shadcn 组件（知识库页面用）
│   └── replay/            # 对局回放子组件（web/ 移植，@ts-nocheck）
├── pages/
│   ├── Dashboard.tsx
│   ├── Replay.tsx         # 对局回放（web/ 移植，@ts-nocheck）
│   ├── kb/                # 知识库三页（web-kb/ 移植）
│   └── ...
├── lib/
│   ├── utils.ts           # cn + deepCamelize + 格式化工具
│   ├── hooks.ts           # usePolling 等
│   ├── useEpisode.ts      # 对局数据 hook（web/ 移植）
│   └── usePlayback.ts     # 回放控制 hook（web/ 移植）
├── constants/
│   ├── evidence.ts        # 证据分级定义（web/ 移植）
│   └── ui.ts              # 界面文案与配色（web/ 移植）
├── mock/                  # 对局回放 mock 数据（web/ 移植，模块 import）
└── types/
    ├── index.ts           # Dashboard + 通用类型
    └── kb.ts              # 知识库类型（camelCase，web-kb/ 移植）
```

## 证据分级

7 档统一渲染：fact / annotated / cv / retrieved / inferred / estimated / mock。
retrieved / inferred / estimated 用虚线边框标注"非事实"。

## 注意

- web/ 移植的文件（episode.ts、Replay.tsx、replay/*、useEpisode.ts、usePlayback.ts、constants/*）标注了 `@ts-nocheck`，后续可逐步补类型。
- public/mock/ 是 Dashboard + 知识库的 mock 数据（fetch 加载）；src/mock/ 是对局回放的 mock 数据（模块 import）。
