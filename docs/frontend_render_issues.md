# 前端真实联调 · 渲染问题记录

> 日期：2026-10-12
> 分支：`agent/qwen`（基线 main `1d74cec`）
> 环境：云沙箱，`python -m uvicorn api.server:app --port 8000` + `VITE_USE_MOCK=false npx vite --port 3001`（vite proxy `/api` → 8000）
> 数据：`python3 scripts/smoke_env.py` 落盘 `results/episodes/mock-3-8-{win,lose}.json`
> 采集方式：无头 Chrome（1600×1000，dsf 1.5）逐路由访问，记录 **接口状态码 / 控制台错误 / 页面正文**，截图存 `docs/screenshots/`
> 截图：`dashboard.png`、`live.png`、`replay.png`、`resources.png`、`training.png`、`kb-rag.png`、`kb-graph.png`、`kb-operator.png`

---

## 一、8 路由验证结果

| # | 路由 | 截图 | 接口 | 结论 |
|---|---|---|---|---|
| 1 | `/` Dashboard | `dashboard.png` | health 200 / live·snapshot 200 / account 200 / progress 200 / tasks 200 / training·runs 200 / **source-stone 503** | ⚠️ 六卡片中五个正常，源石卡原为**永久"加载中…"**（已修，见 §3.1） |
| 2 | `/live` | `live.png` | live·snapshot 200 ×2（轮询） | ✅ mock 帧正常渲染：费用 15、可部署格 A1–B5、敌情（重装×3 估算 / 士兵×5 CV确认）、VLM 观点、决策流时间线（第1步 置信90% 1.2s + deploy 动作 + 检索来源）。**WS 未接入**，页面自述"WS 待接入，当前轮询快照"，实测无 `/ws/live` 请求（见 §4.1） |
| 3 | `/replay` | `replay.png` | episodes 200 / episode/{id} 200 / steps 200 | ✅ 能列出对局、能选中、时间轴与单步详情都渲染（默认选中 `mock-3-8-lose`，3 个时间节点，点击第 3 步出现「步 3 · 游戏状态（决策前）」）。**但结构化状态缺失导致多面板空态**（后端 Issue #1/#2，见 §4.2） |
| 4 | `/resources` | `resources.png` | **source-stone 503** / account 200 / progress 200 | ✅ 三块**分开显示**（源石三档卡 / 账号资源卡 / 主线进度卡各自独立），账号与进度数据正常；源石卡原为"加载中…"（已修） |
| 5 | `/training` | `training.png` | training·runs 200 | ✅ 空态正确：「暂无训练 run · V100 上启动 SFT 后在此展示 loss/eval」+ 顶部 mock 声明 |
| 6 | `/kb/rag` | `kb-rag.png` | search 200 | ✅ 检索链路通（`q=能天使的技能是什么` 已 URL 编码，200）。返回命中为空 → 显示空结果态，无报错 |
| 7 | `/kb/graph` | `kb-graph.png` | **subgraph/3-8 503** / recommend 200 | ❌→✅ 原为**未捕获异常**（`pageerror: API /api/graph/subgraph/3-8 失败: 503`），整页只剩骨架；已修为降级卡片（见 §3.2） |
| 8 | `/kb/operator` | `kb-operator.png` | operator/阿米娅 200 | ✅ 干员详情正常渲染，侧栏与导航齐全 |

**接口层面汇总**：8 路由共 2 个接口报错，均为后端 503（`/api/resources/source-stone`、`/api/graph/subgraph/{stage}`）；无 404、无前端请求构造错误、中文参数编码正常。

---

## 二、上一轮 3 条契约修复的对齐情况（实测）

| 契约项 | 后端实测 | 前端渲染 | 结论 |
|---|---|---|---|
| **evidence 8 档全集（含 `vlm` 与 `annotated`）** | `agent/output_schema.py::EvidenceLevel` 仍是 **7 档**：`fact / retrieved / inferred / cv / estimated / annotated / mock`，**没有 `vlm`** | `types/index.ts::EvidenceLevel` 是另一套 7 档：含 `vlm`、**没有 `annotated`**；`constants/evidence.ts`（回放侧）含 `annotated`、无 `vlm` | ❌ **未对齐**，两边都还不是 8 档全集。目前靠前端 `evidenceLevel()` 的 unknown 兜底不至于崩，但 `vlm` 会渲染成灰色"未标注"徽章。详见 §4.3 |
| **步号从 1 开始** | `EnvStep.step` = `1,2,3,4,5…` ✅ | 时间轴直接用 `step` 显示编号，节点序号与后端一致 ✅ | ✅ **已对齐** |
| **`elapsed_sec` 不再恒为 0** | `trace.decision.elapsed_sec` = `0,1,2,3,4` ✅（决策时刻，正确）；但 **`trace.elapsed_sec` 仍恒为 `0.0`**（10 步全 0）；`EnvStep.elapsed_sec` = `1,2,3…` ✅ | 前端时间轴/趋势图用的是 `EnvStep.elapsedSec`（执行后），显示正确；未使用 `trace.elapsed_sec` | ⚠️ **部分修复**：`decision.elapsed_sec` 已对，`trace.elapsed_sec` 仍是 0（Issue #4 未完全关闭）。前端暂不受影响，但契约上这两个字段语义应写清 |

---

## 三、本轮已修（前端侧，全部在 `frontend/`）

### 3.1 后端 503/404 时卡片永久停在"加载中…"

- **现象**：`/api/resources/source-stone` 返回 503 时，Dashboard 源石卡与 `/resources` 源石三档卡都只显示"加载中…"，**永远不会变成错误态**，用户看不出是后端挂了还是数据没到。
- **根因**：`usePolling` 其实已经返回 `{ data, error, loading }`，但所有调用方只判 `!data`，`error` 被完全忽略。
- **修法**：
  - `components/Card.tsx` 新增 `ErrorState`（红色虚线框 + 主文案 + 处置提示 + 原始错误详情），与 `EmptyState`（"暂无数据"）语义区分开；
  - `pages/Resources.tsx` 三块卡片分别消费 `sourceStone.error / account.error / progress.error`；
  - `pages/dashboard/ResourcesCard.tsx` 新增三个可选 error props，源石区渲染 `ErrorState`，账号/进度失败时在指标下给一行降级说明（值仍显示 `—`）；
  - `pages/Dashboard.tsx` 把 error 透传下去。
- **验证**：修复后 `/resources` 正文出现「源石三档取数失败 · /api/resources/source-stone 返回错误（常见为 503） · API … 失败: 503」，且**账号资源与主线进度仍正常显示**（局部降级，不牵连整页）。

### 3.2 `/kb/graph` 未捕获 503 → 整页 pageerror

- **现象**：`pageerror: API /api/graph/subgraph/3-8 失败: 503`，页面只剩标题与关卡选择器，子图区域空白且控制台报错。
- **根因**：`GraphPage` 的 `useEffect` 里 `Promise.all([...])` 没有 try/catch，`fetchJsonOrNull` 只吞 404、503 会抛出，异常在 async IIFE 里冒泡成未处理拒绝。
- **修法**：包 try/catch → 新增 `loadError` 状态 → 清空 nodes/links → 渲染降级卡片（说明"通常是知识图谱尚未构建，运行 `bash scripts/build_graph.sh` 后刷新"，并附原始错误）；同时把原 `notFound` 分支限定为 `notFound && !loadError`，避免两种空态叠加。
- **验证**：修复后 `pageerror` 消失，控制台只剩浏览器对 503 响应的常规网络日志；页面显示降级卡片 + `recommend` 数据仍可用。

### 3.3 Dashboard 有一条与业务无关的 404

- **现象**：控制台 `Failed to load resource: 404`，但 `/api/*` 全部有账可查（12 次调用，除 source-stone 外全 200）。
- **根因**：`frontend/index.html` 没有 favicon 声明，浏览器自动请求 `/favicon.ico` → 404。
- **修法**：加内联 SVG data-URI favicon（折线图 + 高亮点，与产品调性一致），不引入二进制文件。
- **验证**：修复后重跑，Dashboard 的失败响应只剩 `503 /api/resources/source-stone` 一条。

---

## 四、待后端处理（已开 Issue，前端不自行改后端）

### 4.1 `/api/resources/source-stone` 返回 503（**本轮新开 Issue**）

`docs/frontend_integration_report.md` 里记录该接口是"真实数据 200（源石三档）"，本轮实测为 **503**，且 Dashboard 与 `/resources` 两处都受影响。需要后端确认是数据源未就绪还是回归。前端已按 §3.1 做降级，但**数据本身仍然拿不到**。

### 4.2 `/replay` 在真实模式下多面板空态（既有 Issue #1 / #2）

`/api/episode/{id}/steps` 的 `trace` 里仍**没有结构化 `state`**（实测 `trace` 键为 `bridge / command / decision / elapsed_sec / execute / knowledge / latency_ms / reflection / state_excerpt / step`，`'state' in trace == False`），对局级也没有 `map`。因此 API 模式下这些面板只能走空态：

| 面板 | 状态 |
|---|---|
| 决策理由 / 检索知识 / 执行动作 / 耗时 / 反思 | ✅ 正常（`trace` 里有） |
| 地图与部署（10×10 网格、占格、干员朝向） | ❌ 空态"无地图数据" |
| 敌情与波次时间轴、VLM 局势卡 | ❌ 空态 |
| 手牌 / 已部署干员 / 技能 | ❌ 空态 |
| 费用条（`limit`/`source`/`state`/`confidence`）、耐久、部署位 x/9 | ⚠️ 只剩执行后的裸 `cost`/`life`，读数来源与可信度标签无法显示 |

`state_excerpt` 里有全部信息的**文本形式**，前端可以正则降级解析，但那是兜底不是方案（见 Issue #1）。

### 4.3 evidence 分级两套口径未统一（既有 Issue，契约冻结项）

- 后端 `EvidenceLevel`（7 档，含 `annotated`，无 `vlm`）
- 前端 `types/index.ts`（7 档，含 `vlm`，无 `annotated`）
- 前端 `constants/evidence.ts`（7 档，含 `annotated`，无 `vlm`）
- `perception.schemas.SpawnSource` 实际会产出 `vlm` 与 `timer:annotated`

建议契约定为 **8 档全集**：`fact / annotated / cv / retrieved / inferred / vlm / estimated / mock`，并给出每档的展示语义（哪些必须虚线/降权）。前端三处收敛成一处即可，改动量很小，但**必须等契约定稿**，否则来回返工。

### 4.4 `trace.elapsed_sec` 恒为 0（既有 Issue #4，部分修复）

`trace.decision.elapsed_sec` 已修好（`0,1,2,3,4`），但 `trace.elapsed_sec` 10 步全是 `0.0`。建议要么让它等于 `decision.elapsed_sec`（决策时刻），要么直接删掉这个字段，避免两个同名字段语义不一致。

### 4.5 `/ws/live` 前端未接入（既有状态，非回归）

`/live` 页当前是 3s 轮询 `/api/live/snapshot`，页面自己也标注了"WS 待接入"。实测无任何 `/ws/*` 请求。后端 WS 是否可用**本轮未验证**（前端没连，无法从前端侧证明）；接入属于前端工作，但需要后端确认 WS 消息格式与心跳约定后再做，故先记录不擅自动手。

---

## 五、Dashboard 四项自查（任务 C）

| 项 | 结论 | 依据 |
|---|---|---|
| **1. 实时数据轮询（真实模式）** | ✅ 正常 | `usePolling` 在 `VITE_USE_MOCK=false` 下按间隔真实请求：Dashboard 一次访问内观察到 `live/snapshot` 被请求 2 次（3s 间隔）、`health` 2 次（5s 间隔），资源三接口 10s 间隔并发；`/live` 页同样观察到 snapshot 轮询。轮询在组件卸载时 `clearTimeout` + `alive` 双保护，无泄漏 |
| **2. 错误处理（503/404 优雅降级）** | ❌→✅ 已修 | 修复前 503 会让源石卡永久"加载中…"、图谱页抛未捕获异常；修复后两处均降级为明确的错误态卡片，**且只降级出错的那一块**（同页其他卡片数据照常显示）。404 由 `fetchJsonOrNull` 统一转 `null`，各页走空态 |
| **3. 加载状态** | ✅ 有，且现在与错误态区分 | 数据未到时显示"加载中…"（`EmptyState`/文案），失败时显示 `ErrorState`；两者不再混用同一个"加载中…" |
| **4. 快捷入口 5 个链接** | ✅ 全部可用 | `QuickLinksCard` 的 5 个 `Link`：`/live`、`/replay`、`/kb/rag`、`/kb/graph`、`/kb/operator` —— 本轮已逐个实际访问，均 200 且页面有内容（`/kb/graph` 为降级态但可访问、不白屏） |

---

## 六、复现方式

```bash
# 1. 造对局数据（results/ 已 gitignore）
python3 scripts/smoke_env.py

# 2. 起后端
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000

# 3. 起前端（真实模式）
cd frontend && npm install && VITE_USE_MOCK=false npm run dev   # http://127.0.0.1:3001

# 4. 逐路由核对（本文所有结论的来源）
curl -s localhost:8000/api/resources/source-stone -o /dev/null -w '%{http_code}\n'   # 503
curl -s localhost:8000/api/graph/subgraph/3-8 -o /dev/null -w '%{http_code}\n'       # 503
curl -s localhost:8000/api/episode/mock-3-8-win/steps | python3 -c "
import json,sys; s=json.load(sys.stdin)['steps']
print('step 起始:', s[0]['step'])
print('EnvStep.elapsed_sec:', [x['elapsed_sec'] for x in s][:5])
print('trace.elapsed_sec  :', [x['trace']['elapsed_sec'] for x in s][:5])
print('trace.decision.elapsed_sec:', [x['trace']['decision']['elapsed_sec'] for x in s][:5])
print('trace 有结构化 state 吗:', 'state' in s[0]['trace'])"
```
