# frontend/ — 统一前端最终形态（Dashboard 外壳骨架）

React 19 + Vite 7 + Tailwind 3 + React Router 7（版本与 `web-kb/` 实际依赖对齐，
便于后续把 `web-kb/` 与 Qwen `web/` 的页面并入）。

## 这是什么

按 `docs/dashboard_design.md` 落地的**统一外壳 + 总览 Dashboard 骨架**：
顶栏（环境/模块数/显存/USE_MOCK）、左侧导航、六个总览卡片。当前**全部走 mock**，
不依赖后端，也不修改 `web/`、`web-kb/` 的任何文件。

## 路由

| 路径 | 页面 | 状态 |
| --- | --- | --- |
| `/` | 总览 Dashboard（系统状态/实时对局/资源/任务/训练/快捷入口） | 骨架（mock） |
| `/live` | 实时对局（完整决策流） | 骨架（mock；真实走 `/ws/live`，后端🆕） |
| `/replay` | 对局回放 | 占位，等 Qwen `web/` |
| `/resources` | 资源管理（源石三档/账号/进度） | 骨架（mock） |
| `/training` | 训练监控（loss/eval） | mock 示例曲线，V100 接入真实数据 |
| `/kb/rag` `/kb/graph` `/kb/operator` | 知识库 | 占位，等并入 `web-kb/` |

## 数据层

- `src/api/client.ts`：`VITE_USE_MOCK`（默认 true）读 `public/mock/*.json`；
  设为 `false` 时请求同源 `/api/*`（dev 经 vite proxy → `http://127.0.0.1:8000`）。
- 所有后端返回经 `src/lib/utils.ts` 的 `deepCamelize`：wire 是 snake_case，
  组件只见 camelCase；类型集中在 `src/types/index.ts`。
- `public/mock/` 的 schema 与 `docs/dashboard_design.md` 定义的返回格式一致，
  切真实接口时无需改组件。

## 证据分级

`src/components/EvidenceBadge.tsx` 是从两个前端抽出的**公共**七色标签：
fact / retrieved / inferred / estimated / cv / vlm / mock；
其中 retrieved / inferred / estimated 用虚线边框，表示非确定事实。合并后两个 web 统一复用。

## 运行

```bash
cd frontend
npm install
npm run dev       # http://localhost:3001（mock 模式）
npm run build     # tsc -b && vite build
# 真实后端：VITE_USE_MOCK=false npm run dev（需先 python -m api.server 起在 :8000）
```

## 红线

- 游戏截图只在本机内存/本地网络流转，**不入 git、不落库**；mock 不使用任何真实游戏画面。
- GPU/训练数值无 V100 时为空态或明确标注的 mock 示例，不制造假数据当真。
- 抽卡建议只使用源石"立即可拿 + 短期"两档，长期档仅资源页展示。
