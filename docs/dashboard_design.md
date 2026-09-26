# 总览 Dashboard 设计稿（docs/dashboard_design.md）

> 状态：**设计稿，不含代码**（第十六批任务二）。目标读者：合并 `web-kb/`（Kimi）与
> `web/`（Qwen，待传输到位）时做统一外壳与路由的人。
> 约束：前端只消费后端 HTTP/WS API（方案 A）；所有数值必须可溯源到现有 API，
> 尚未存在的接口在第 3 节明确标"🆕 需新增"，不允许前端写死/编造；GPU 数据 V100 后才有。

## 1. 页面布局

三栏式控制台，最小设计宽度 1280px，窄屏时左侧导航折叠为图标栏。

```
┌────────────────────────────────────────────────────────────────────────┐
│ 顶栏 TopBar：Logo/项目名 │ 环境(Mock/V100) │ Agent运行/暂停 │ 全局时延 │ 显存 │ 设置 │
├──────────┬─────────────────────────────────────────────────────────────┤
│ 左侧导航  │ 主内容区（按路由切换）                                          │
│ ───────  │                                                                 │
│ 总览      │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│ 实时对局  │  │ 系统状态卡     │ │ 资源仪表盘卡  │ │ 训练进度卡    │            │
│ 对局回放  │  └──────────────┘ └──────────────┘ └──────────────┘            │
│ 知识库 ▸  │  ┌────────────────────────────┐ ┌──────────────────────────┐  │
│   RAG检索 │  │ 实时对局卡（截图+状态+决策流） │ │ 任务队列卡（当前/下一步）  │  │
│   知识图谱 │  └────────────────────────────┘ └──────────────────────────┘  │
│   干员详情 │  ┌────────────────────────────────────────────────────────┐  │
│ 训练监控  │  │ 快捷入口（回放/RAG/图谱/干员/资源）                         │  │
│ 资源管理  │  └────────────────────────────────────────────────────────┘  │
└──────────┴─────────────────────────────────────────────────────────────┘
```

- **顶栏 TopBar**：全局信息，任何页面常驻。左侧项目名与当前环境徽标
  （`mock` / `V100`，取自健康检查，禁止前端猜）；中部 Agent 运行/暂停开关（🆕 控制接口，
  第一版可只展示状态不做开关）；右侧全局 P50 时延、显存占用、后端连接状态。
- **左侧导航 SideNav**：一级=总览/实时对局/对局回放/训练监控/资源管理；
  "知识库"为可展开二级（RAG 检索、知识图谱、干员详情，直接复用 web-kb 三个页面）。
- **主内容区**：总览页为卡片网格（2 列），每张卡片可"查看详情"跳到对应一级页。
  卡片统一带：标题、刷新时间戳、数据来源标注（API/evidence 分级）、空态与 Mock 态。

## 2. 模块清单（显示什么 + 数据从哪来）

### 2.1 系统状态卡
- 显示：perception / agent(慢·快·VLM) / knowledge(RAG·图谱·MCP) / action / env 各模块
  **在线状态**；各链路延迟指标（快通道 CV、VLM 慢通道、决策循环各阶段耗时，六段延迟）；
  **显存占用**（已用/总量、利用率）；后端版本与运行环境（mock/真机）。
- 数据：现有 `GET /api/health`（仅基础存活）；模块状态与延迟、显存需要扩展/新增（见 3.1）。
- Mock 态：全部模块显示为 mock、延迟显示占位灰字"—"，显存显示 N/A（不画假曲线）。

### 2.2 实时对局卡
- 显示：左侧**当前屏幕截图**（画面流，标注 estimated/cv 的敌情框）；
  右上**结构化状态**（费用、可部署干员、技能冷却、敌人波次、可部署格子）；
  右下**决策流时间线**：每步 `reasoning → action → confidence → knowledge_used`，
  知识引用可点击溯源；顶部放 VLM 慢通道的 `situation / strategic_advice`（2s 一次）。
- 数据：事后数据已有 `/api/episode/{id}/steps`（A3 日志合流后的完整可解释数据）；
  **实时流没有接口**，需新增 WebSocket/轮询（见 3.2）。Mock 模式下可回放最近一局
  episode 当作"实时"演示。

### 2.3 资源仪表盘卡
- 显示：至纯源石、合成玉、龙门币、拥有干员数、主线关卡进度（已通/总数）；
  源石下钻三档：**立即可拿 / 短期(1-2天) / 长期**——总览可显示三档总数，
  但"抽卡建议"入口只把前两档喂给 Agent（口径与 `source_stone_tracker` 一致）。
- 数据：
  - 源石分档：后端库 `knowledge/source_stone_tracker.py` 已实现，🆕 需包一个只读 API；
  - 合成玉/龙门币/干员数：`perception/gacha.py`、`perception/shop.py` 目前只有
    mock 状态解析，**未持久化、无 API**（🆕，真机识别 + 账号态存储后才有真值）；
  - 关卡进度：episode 结算 + PRTS 关卡台账可推算已推章节（🆕 进度上报/落库）。
- Mock 态：合成玉 12000 / 源石 18 等来自 MockGachaScreenParser，必须打 mock 标。

### 2.4 任务队列卡
- 显示：当前正在执行的任务（如"第 4 步：部署术师到 B3"或"构建 RAG 向量库"）、
  排队中的下一步计划、任务状态（运行/等待/失败/完成）与耗时；支持取消（后期）。
- 数据：🆕 全新任务编排接口（见 3.4）。第一版若没有任务系统，卡片显示"任务系统未接入"，
  不编造队列；可先用 decision_loop 的当前 step 做最小展示。

### 2.5 训练进度卡
- 显示：SFT loss 曲线（train/eval）、eval 指标（准确率/格式合规率/人工评分占位）、
  当前 epoch/step、LoRA 配置摘要、checkpoint 列表；预留 DPO 面板。
- 数据：🆕 训练侧落 metrics 文件（`results/`，gitignore）+ 只读 API（见 3.5）。
  V100 上线前该卡显示"未接入（TODO-V100）"，**不画假 loss**。

### 2.6 快捷入口卡
- 对局回放（→ `/replay`）、RAG 检索（→ `/kb/rag`）、知识图谱（→ `/kb/graph`）、
  干员详情（→ `/kb/operator`）、资源管理（→ `/resources`）；每个入口带一句最近数据摘要
  （如"最近一局：3-8 通关，用时 4m12s""图谱：节点 N / 边 M"，复用 graph overview）。

## 3. 数据依赖：现有 API vs 需新增

### 3.1 已有（`api/server.py`，无需改动即可对接）
| 用途 | 接口 |
| --- | --- |
| 后端存活/环境 | `GET /api/health` |
| 干员/技能/敌人/关卡 | `GET /api/operator/{name}`、`/api/skill/{operator}/{skill_name}`、`/api/enemy/{name}`、`/api/stage/{stage_id}` |
| RAG 检索 | `GET /api/search?q=&k=&doc_type=`（返回 `{hits:[...]}`，score 为 1−cosine，0-1） |
| 干员推荐 | `GET /api/recommend/{stage_id}`（含 found=false 空推荐态） |
| 对局列表/详情/逐步 | `GET /api/episodes`、`/api/episode/{id}`（默认不内嵌 steps）、`/api/episode/{id}/steps` |
| 图谱 | `GET /api/graph/overview`、`/graph/node/{id}`、`/graph/subgraph/{stage_id}` |

### 3.2 🆕 需新增：实时对局
- `GET /api/live/screenshot`（返回当前帧 JPEG，低频轮询兜底）**和/或**
  `WS /ws/live`（推送帧 + GameState 增量 + DecisionLog）。建议优先 WS，截图走二进制帧、
  状态走 JSON 帧；轮询作为降级。
- 后端在 `ArknightsEnv` 跑局时把 StepRecord + 合流日志推到一个内存 pub/sub，不落盘也可推。
- 注意版权：截图属游戏画面，**只在本机内存/本地网络传输，不落库不入 git**。

### 3.3 🆕 需新增：资源与源石
- `GET /api/resources/source-stone?completed_normal=&completed_raid=&current_stone=`
  或 `POST`（进度在 body，避免 URL 过长）：调用 `SourceStoneTracker.analyze`，
  返回 `to_dict()`（含三档 tiers 与 `prompt_decision_stone`）；只读、无副作用。
- `GET /api/resources/account`：合成玉/源石/龙门币/干员数（真机阶段由
  gacha/shop 解析 + 账号态存储提供；当前返回 mock 数据并带 `evidence:"mock"`）。
- `GET /api/resources/progress`：主线进度（先可由 source-stone 入参 + episode 结算汇总）。

### 3.4 🆕 需新增：任务队列（可分期）
- `GET /api/tasks`（队列与当前任务）、`POST /api/tasks/{id}/cancel`；
  第一阶段允许只实现只读 `GET`，把"当前对局 step / 后台建库任务"统一成任务视图。

### 3.5 🆕 需新增：训练监控（V100）
- `GET /api/training/metrics?run=`：读 `results/` 下 trainer 落的
  `metrics.jsonl`（step、train_loss、eval_loss、lr、ts）；
- `GET /api/training/runs`：run 列表与配置摘要、checkpoint。
- 训练脚本需要在 V100 阶段补落盘逻辑（CPU 侧只出接口约定，文件不存在返回空列表/409 空态）。

### 3.6 🆕 需扩展：健康检查
- 扩展 `GET /api/health` 返回 `{env, modules:{perception:{online,latency_ms_p50,...},...},
  vram:{used_mb,total_mb,util}, server_version, ts}`；
  vram 用 `nvidia-smi`/torch.cuda 采集，无 GPU 时字段为 null（Mock 环境）。

## 4. 路由设计（React Router）

统一外壳（合并后）的路由表，`/` 是 Dashboard：

| 路径 | 页面 | 来源 |
| --- | --- | --- |
| `/` | 总览 Dashboard（本设计） | 新建外壳 |
| `/live` | 实时对局（截图+状态+决策流） | Qwen `web/`（待到位）/新建 |
| `/replay` | 对局回放列表（episodes） | Qwen `web/` |
| `/replay/:episodeId` | 单局回放（逐步 reasoning/action/奖励） | Qwen `web/`，数据 `/api/episode/{id}/steps` |
| `/resources` | 资源管理（源石三档/账号资源/进度） | 新建（接 3.3） |
| `/training` | 训练监控（loss/eval/runs） | 新建（接 3.5，V100） |
| `/kb/rag` | RAG 检索 | **web-kb `RagPage`** |
| `/kb/graph` | 知识图谱 | **web-kb `GraphPage`** |
| `/kb/operator`、`/kb/operator/:name?` | 干员详情 | **web-kb `OperatorPage`** |
| `*` | 重定向 `/` | — |

- 路由用嵌套结构：`<Route path="/kb" element={<KbLayout/>}>` 包三个 web-kb 页面，
  统一外壳的 TopBar/SideNav 在外层 layout，web-kb 页面只渲染内容区，不重复带自己的导航。
- API client 统一从环境变量取 baseURL（web-kb 已有 USE_MOCK 开关，合并后保留：
  mock 读 `public/mock/`，真机读同源 API），两个 web 共用一个 client 实例。
- score 渲染沿用 web-kb 已对齐的口径：后端 0-1（1−cosine），前端按百分比渲染；
  mock 数据已重写为与真实 API 同 schema，合并不再出现量纲漂移。

## 5. 与现有两个 web 的关系

### 5.1 web-kb/（Kimi，已到位并完成方案 A 改造）
- 现状：独立 SPA，自带路由 `/rag` `/graph` `/operator`，根路径重定向 `/rag`；
  `client.ts` 支持 USE_MOCK（mock 数据在 `public/mock/`，schema 已与后端对齐）。
- 合并方式：**作为知识库子应用挂到 `/kb/*`**：
  - 把三条路由前缀改为 `/kb/rag`、`/kb/graph`、`/kb/operator`；
  - 移除其独立顶层导航/重定向，内容区嵌入统一外壳的 `<Outlet/>`；
  - 复用统一 client 与 CORS（FastAPI 已允许 localhost:*）；
  - 页面内部逻辑、C1-C6 修复、AUDIT.md 记录不动。
- 待办沿用：AUDIT 4.4 的 node 邻居截断不在本次处理——
  "合并后统一处理：node 邻居查询改分组配额，另加反向'推荐关卡'接口"。

### 5.2 web/（Qwen，尚未到位，**不重做、不臆造其实现**）
- 按交接预期承载**对局回放 / 实时对局**页面，挂到 `/replay/*` 与 `/live`。
- 到位后需要核对的对接点（先列验收项，不预设它的代码结构）：
  1. 数据是否消费 `/api/episodes`、`/api/episode/{id}/steps`（A3 合流后的字段）；
  2. evidence 是否按 `{level, source}` 对象渲染（A4 统一形状）；
  3. `/api/episode/{id}` 默认不内嵌 steps，详情页是否正确改调 `/steps`（A6）；
  4. 延迟字段是否用 `latency_ms`、step 起始编号、reward.items 字段名（A7 文档口径）；
  5. 是否自带导航，合并时同样收敛为内容区。
- 若 `web/` 实际页面与预期不同，以其真实页面为准重排路由，不改本设计的信息架构原则。

### 5.3 合并顺序建议
1. 先建统一外壳（TopBar/SideNav/路由表）+ Dashboard 静态骨架，API 未就绪的卡片走空态/Mock；
2. 挂 web-kb 三页到 `/kb/*`（改动最小，已验证可构建）；
3. `web/` 到位后按 5.2 验收并挂 `/replay`、`/live`；
4. 按 3.3→3.6 顺序补后端只读接口，逐卡替换 Mock；
5. 训练卡与实时 WS 留到 V100 阶段，UI 先行但数据通道不造假。

## 6. 跨模块红线（实现时必须遵守）
- 证据分级可视化：fact / retrieved / inferred / mock 用不同样式，retrieved 不得渲染成"确定事实"；
  SpawnTracker 的 estimated 敌情、VLM 建议都要有显式标记。
- 截图/游戏素材只在本地内存与本地网络流转，不入库不入 git；Dashboard 不提供截图云端分享。
- 所有 GPU 相关数值（显存、实时 VLM、训练曲线）在无 V100 时为 null/空态，不生成假数据。
- 抽卡相关建议只用源石前两档；长期档仅在资源管理页展示并标注"不进抽卡决策"。
