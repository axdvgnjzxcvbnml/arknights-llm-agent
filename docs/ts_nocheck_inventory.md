# @ts-nocheck 文件清单

> 日期：2026-09-30
> 总数：26 个文件
> 来源：全部来自 Qwen web/ 对局回放前端的纯 JS/JSX 代码移植
> 状态：待逐步补类型，不影响构建和运行

---

## 总览

| 来源 | 文件数 | 原因 | 优先级 |
|------|--------|------|--------|
| web/ 移植 | 26 | 纯 JS/JSX 转 TS，无类型注解 | 中（不影响功能，影响类型安全） |
| web-kb/ 移植 | 0 | 原生 TSX，类型已在 types/kb.ts 定义 | — |

**为什么需要 @ts-nocheck：**
web/ 前端是纯 JavaScript 项目（无 TypeScript），移植到 frontend（TS 严格模式）时，所有函数参数、返回值、props 都没有类型注解。直接开启类型检查会报数百个 `implicitly has an 'any' type` 错误。为快速跑通构建，先加 `@ts-nocheck` 绕过，后续逐步补类型。

---

## 文件清单

### 1. API 层（1 个）

| 文件 | 来源 | 原因 | 预计补齐 |
|------|------|------|----------|
| `src/api/episode.ts` | web/src/api.js | 纯 JS，normalizeEpisode/normalizeStep 有复杂的字段兜底逻辑，类型需与后端 Episode/StepRecord DTO 对齐 | 高（与后端类型对齐后可补） |

### 2. 页面（1 个）

| 文件 | 来源 | 原因 | 预计补齐 |
|------|------|------|----------|
| `src/pages/Replay.tsx` | web/src/App.jsx | 纯 JSX，主回放页，引用 20+ 子组件和 2 个 hooks，props 类型复杂 | 中（依赖子组件和 hooks 类型补齐后） |

### 3. 组件（21 个）

全部来自 `web/src/components/*.jsx`，纯 JSX，无 props 类型定义。

| 文件 | 功能 | 复杂度 | 预计补齐 |
|------|------|--------|----------|
| `ActionPanel.tsx` | 动作面板（部署/技能/撤退） | 中 | 低 |
| `EnemyPanel.tsx` | 敌人列表面板 | 低 | 低 |
| `EpisodeHeader.tsx` | 对局头部（标题/关卡/结局） | 低 | 低 |
| `EpisodePicker.tsx` | 对局选择器 | 中 | 低 |
| `EvidenceBadge.tsx` | 证据徽章（与 frontend 原生 EvidenceBadge 功能重复，后续可合并） | 低 | 低（建议直接用 frontend 原生组件） |
| `EvidenceLegend.tsx` | 证据分级图例 | 低 | 低 |
| `KnowledgePanel.tsx` | 知识引用面板 | 中 | 中 |
| `LatencyPanel.tsx` | 延迟面板（六段延迟柱状图） | 中 | 低 |
| `MapGrid.tsx` | 地图格子渲染 | 高（canvas/SVG 渲染逻辑复杂） | 中 |
| `OperatorRoster.tsx` | 干员阵容面板 | 中 | 低 |
| `PlaybackControls.tsx` | 回放控制（播放/暂停/速度/进度条） | 中 | 低 |
| `RawLogDrawer.tsx` | 原始日志抽屉 | 低 | 低 |
| `ReasoningPanel.tsx` | 推理过程面板 | 中 | 中 |
| `ReflectionPanel.tsx` | 反思面板 | 低 | 低 |
| `RewardPanel.tsx` | 奖励面板 | 低 | 低 |
| `StatePanel.tsx` | 游戏状态面板（费用/生命/部署数） | 中 | 低 |
| `StepDetail.tsx` | 单步详情（状态+决策+动作+结果） | 高（信息密度大） | 中 |
| `TimelineRail.tsx` | 时间轴轨道 | 中 | 中 |
| `TrendChart.tsx` | 趋势图（recharts） | 中 | 低 |
| `ui.tsx` | UI 基础组件（ErrorBlock/Spinner 等） | 低 | 低 |

### 4. Hooks（2 个）

| 文件 | 来源 | 原因 | 预计补齐 |
|------|------|------|----------|
| `src/lib/useEpisode.ts` | web/src/hooks/useEpisode.js | 纯 JS，对局数据加载 hook，状态类型复杂 | 中 |
| `src/lib/usePlayback.ts` | web/src/hooks/usePlayback.js | 纯 JS，回放控制 hook | 低 |

### 5. 常量（2 个）

| 文件 | 来源 | 原因 | 预计补齐 |
|------|------|------|----------|
| `src/constants/evidence.ts` | web/src/constants/evidence.js | 纯 JS，证据分级定义（7 档颜色/释义），与 frontend 原生 EvidenceBadge 功能重叠 | 低（建议合并到 frontend 原生 constants） |
| `src/constants/ui.ts` | web/src/constants/ui.js | 纯 JS，界面文案与配色常量（动作类型/结局/职业配色/延迟阶段） | 低 |

---

## 补齐优先级建议

### P0（先做，收益高）
1. **`api/episode.ts`** — 与后端 Episode/StepRecord DTO 类型对齐，是所有回放页面的类型基础
2. **`constants/evidence.ts` + `constants/ui.ts`** — 纯常量，补类型最简单，且可与 frontend 原生合并
3. **`lib/usePlayback.ts`** — 逻辑简单，补类型快

### P1（其次）
4. **简单组件**（EnemyPanel/EpisodeHeader/EvidenceLegend/RewardPanel/RawLogDrawer/ui 等）— props 少，补类型快
5. **`lib/useEpisode.ts`** — 依赖 api/episode.ts 类型补齐后

### P2（最后）
6. **复杂组件**（MapGrid/StepDetail/TimelineRail/ReasoningPanel/KnowledgePanel）— props 多、逻辑复杂
7. **`pages/Replay.tsx`** — 依赖所有子组件和 hooks 类型补齐后

---

## 可合并/可删除的冗余

| 文件 | 问题 | 建议 |
|------|------|------|
| `components/replay/EvidenceBadge.tsx` | 与 frontend 原生 `components/EvidenceBadge.tsx` 功能重复（都是 7 色证据渲染） | 建议删除 replay 版，统一用 frontend 原生版 |
| `constants/evidence.ts` | 与 frontend 原生 EvidenceBadge 的证据分级定义重叠 | 建议合并到 frontend 原生 constants |

---

## 补齐方式建议

1. **从后端 DTO 推导类型**：Episode/StepRecord/Reward 等类型已在 `env/episode_store.py` 和 `agent/output_schema.py` 定义，可直接推导 TS 类型
2. **渐进式补齐**：每次只补 2-3 个相关文件，补完即删 `@ts-nocheck`，跑构建验证
3. **优先补 props 类型**：组件的 props 接口定义后，大部分 `implicit any` 错误就消失了
4. **用 `typeof` 推导**：对于复杂的状态对象，可用 `typeof` 从 mock 数据推导类型

---

## 验证标准

每个文件补齐类型后：
1. 删除文件顶部的 `// @ts-nocheck`
2. 跑 `npm run build`（含 `tsc -b`），确认无该文件的类型错误
3. 跑 `npm test`，确认前端测试通过
4. 手动验证该组件/页面功能正常

---

## 进度跟踪

| 阶段 | 已补齐 | 剩余 | 完成率 |
|------|--------|------|--------|
| 初始 | 0 | 26 | 0% |

（每次补齐后更新此表）
