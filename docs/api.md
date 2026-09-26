# 后端 API 文档（FastAPI）

后端把知识库工具、对局日志、知识图谱封装成 HTTP 接口，供前端 / 可视化 / 答辩演示调用。

- 实现：`api/server.py`（`create_app(...)` 工厂，默认实例 `app`）
- 交互式文档（OpenAPI / Swagger）：服务启动后访问 <http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>
- 单元测试：`tests/test_api.py`（全部 mock，不依赖真实数据 / GPU）

## 启动

```bash
# 依赖已在 requirements.txt（fastapi / uvicorn / httpx[测试]）
pip install -r requirements.txt

# 方式一
uvicorn api.server:app --host 127.0.0.1 --port 8000

# 方式二（端口可用环境变量覆盖）
ARK_API_PORT=8000 python -m api.server
```

## 证据分级（每个响应都带 `evidence`）

| 值 | 含义 | 适用接口 |
|----|------|----------|
| `fact` | 解析自 PRTS Wiki 的结构化事实 | operator / skill / enemy / stage、图谱统计 |
| `retrieved` | RAG **检索到的参考资料**，不是事实判断，需结合上下文核实 | search |
| `inferred` | 知识图谱规则**推断**，非 PRTS 官方结论，不得当事实引用 | recommend、子图中的 RECOMMENDS 边 |

> 对局逐步接口里每步的 `evidence` 统一是 `{"level": <上表值>, "source": <来源名>}`
> 对象数组（不再是 `"fact:PRTS"` 字符串）；更丰富的引用明细见该步 `trace.knowledge.citations`。
> 视觉链路另可能出现 `cv`（视觉确认）/ `estimated`（均匀估算）/ `mock`（合成数据），均非事实升级。

## 状态码约定

- `200`：调用成功。业务上"实体不存在"**不报错**，而是返回 `{"found": false, "message": ...}`，
  前端据 `found` 字段判断。
- `404`：对局 id / 图谱节点 / 关卡子图不存在。
- `400`：对局 id 含非法字符（仅允许字母、数字、`_`、`-`）。
- `422`：查询参数类型 / 取值非法（如 `level=-1`、`k=99`）。
- `503`：知识图谱尚未构建（缺 `data/graph/arknights_graph.graphml`），
  先运行 `bash scripts/build_graph.sh`。

## CORS

允许本机开发服务器跨域：`http(s)://localhost:<任意端口>` 与 `http(s)://127.0.0.1:<任意端口>`。
前端（Vite 默认 5173 等）可直接调用。

## 懒加载 / 资源占用

导入 `api.server` **不会**拉起 torch / chromadb / bge / mcp。PRTS JSON、向量库、
83M 图谱均在首次请求相关接口时才加载（图谱首查约 9 秒，之后驻留内存）。
MCP 工具经 `knowledge/mcp_tools/tools_*.py` 纯函数复用，**不** import FastMCP 的 `server.py`。

---

## 一、知识工具

### GET `/api/operator/{name}`

查询干员完整信息（职业 / 星级 / 分支 / 标签 / 势力 / 特性 / 费用 / 全部技能）。

- 路径参数 `name`：干员页面标题/中文名，如 `能天使`、`阿米娅(近卫)`。
- 返回：`OperatorOut`，`evidence=fact`。

```bash
curl "http://127.0.0.1:8000/api/operator/能天使"
```

```json
{
  "found": true,
  "evidence": "fact",
  "name": "能天使",
  "display_name": "能天使",
  "star_rating": 6,
  "class": "狙击",
  "branch": "速射手",
  "position": "远程",
  "deploy_cost": "12",
  "trait": { "branch": "速射手", "desc": "..." },
  "skills": [ { "name": "过载模式", "type": "攻击回复", "levels": [ ... ] } ],
  "source_url": "https://prts.wiki/w/能天使"
}
```

> 注：JSON 用别名输出，职业字段名是 `class`（对应内部 `operator_class`）。

### GET `/api/skill/{operator}/{skill_name}`

查询某干员单个技能详情（机制类型 + 各级效果 / 技力 / 持续）。

- `operator`：干员名；`skill_name`：技能名（精确优先、包含兜底）。
- 返回：`SkillOut`，`evidence=fact`。

```bash
curl "http://127.0.0.1:8000/api/skill/能天使/过载模式"
```

```json
{
  "found": true,
  "evidence": "fact",
  "operator": "能天使",
  "skill": { "name": "过载模式", "type": "攻击回复",
             "levels": [ { "level": "10", "cost": "自动触发", "duration": "15秒" } ] }
}
```

### GET `/api/enemy/{name}`

查询敌人分级属性。

- 路径 `name`：敌人名，如 `碎骨`。
- 查询参数 `level`（可选，整数 ≥0）：只取指定级别；省略返回全部级别。非法值返回 422。
- 返回：`EnemyOut{ levels: [...] }`，`evidence=fact`。

```bash
curl "http://127.0.0.1:8000/api/enemy/碎骨?level=0"
```

### GET `/api/stage/{stage_id}`

查询关卡信息卡 + 本关敌情。

- 路径 `stage_id`：关卡编号，如 `3-8`。
- 返回：`StageOut{ info, enemies: [{name,count,level,position,stats}] }`，`evidence=fact`。

```bash
curl "http://127.0.0.1:8000/api/stage/3-8"
```

### GET `/api/search`

RAG 语义检索知识片段。**结果为 `evidence=retrieved` 的参考资料，不是事实判断。**

| 参数 | 类型 | 说明 |
|------|------|------|
| `q` | string，必填 | 自然语言问题 |
| `k` | int，1–20，默认 5 | Top-K |
| `doc_type` | string，可选 | `operator` / `enemy` / `stage` / `guide` |

```bash
curl "http://127.0.0.1:8000/api/search?q=能天使的技能是什么&k=5&doc_type=operator"
```

```json
{
  "found": true,
  "evidence": "retrieved",
  "query": "能天使的技能是什么",
  "embedding_backend": "bge-small-zh-v1.5",
  "hits": [
    { "content": "...", "score": 0.83, "source": "能天使", "type": "operator",
      "section": "skill", "url": "https://prts.wiki/w/能天使", "evidence": "retrieved" }
  ],
  "note": "本结果为 RAG 检索到的参考资料（evidence=retrieved），不是事实判断……"
}
```

> 注：命中类型字段名是 `type`（对应内部 `doc_type`）。

### GET `/api/recommend/{stage_id}`

按关卡敌情经图谱规则推荐干员组合。**`evidence=inferred`，非官方结论。**

| 查询参数 | 说明 |
|----------|------|
| `classes` | 职业白名单，逗号分隔，如 `术师,狙击` |
| `min_star` / `max_star` | 星级区间（1–6） |
| `top_n` | 返回数量（1–30，默认 8） |
| `exclude` | 排除干员，逗号分隔 |

```bash
curl "http://127.0.0.1:8000/api/recommend/3-8?classes=术师,狙击&min_star=5"
```

```json
{
  "found": true,
  "evidence": "inferred",
  "stage_id": "3-8",
  "constraints_applied": { "classes": ["术师", "狙击"], "min_star": 5 },
  "operators": [
    { "operator": "艾雅法拉", "class": "术师", "star": 6, "score": 3.2,
      "matched_enemies": ["碎骨"], "matched_rules": ["high_resistance->caster"],
      "evidence": "inferred" }
  ],
  "note": "本结果由规则推断（evidence=inferred）……并非 PRTS Wiki 官方结论……"
}
```

---

## 二、对局日志

对局以 JSON 存于 `results/episodes/<id>.json`，内容为
`env.arknights_env.EpisodeLog.model_dump()`（`results/` 已 gitignore）。
`env.run_episode(save=True)` 结束时会**自动落盘**（EpisodeStore 统一入口，环境与 API 共用）：

```python
# 自动落盘（推荐）
log = env.run_episode("3-8", save=True, episode_id="ep-win")

# 也可显式写 / 读（存储实现已下沉到 env 包，不依赖 FastAPI）
from env.episode_store import EpisodeStore
EpisodeStore().save("ep-win", episode_log.model_dump())
```

### GET `/api/episodes`

对局列表，返回每局**轻量摘要**（不含 `steps` 大字段）。

```bash
curl "http://127.0.0.1:8000/api/episodes"
```

```json
{ "found": true, "count": 1,
  "episodes": [
    { "id": "ep-win", "stage_id": "3-8", "outcome": "win", "backend": "mock",
      "step_count": 10, "duration_sec": 9.5, "total_reward": 87.0 } ] }
```

### GET `/api/episode/{id}`

返回一局摘要。`id` 仅允许字母数字 `_ -`。
**默认不内嵌 steps**（避免重复传输）；需要完整逐步数据时加 `?embed_steps=true`，
或调用下面的 `/steps` 接口。

```bash
curl "http://127.0.0.1:8000/api/episode/ep-win"                  # 不带 steps
curl "http://127.0.0.1:8000/api/episode/ep-win?embed_steps=true" # 带 steps
```

```json
{
  "id": "ep-win",
  "found": true,
  "stage_id": "3-8",
  "outcome": "win",
  "backend": "mock",
  "duration_sec": 9.5,
  "step_count": 10,
  "total_reward": 87.0,
  "embedded_steps": false,
  "reward": {
    "outcome": "win", "total": 87.0,
    "summary_line": "总分 87 = 通关+100 + 漏怪-10(1点) + 费用溢出-3(3.0s)",
    "items": [ { "name": "clear", "delta": 100.0, "why": "通关奖励" } ] },
  "episode": { "stage_id": "3-8", "outcome": "win", "reward": { ... } }
}
```

> `reward.items` 字段名为 `name` / `delta` / `why`；`summary_line` 是序列化后仍存在的
> 字符串字段（不是方法）。

### GET `/api/episode/{id}/steps`

返回逐步完整记录。除了 EnvStep 摘要字段，每步还带 `trace`——与决策循环
`StepRecord` 合流后的完整可解释数据：`knowledge`（引用列表）、`decision`
（结构化 reasoning / knowledge_used / confidence）、`bridge`、`command`、
`reflection`、六段延迟 `latency_ms`。

- 步编号 `step` **从 1 开始**（EnvStep 口径）。
- `evidence` 为统一的 `{ "level", "source" }` 对象数组；`level` 取
  fact / retrieved / inferred / cv / estimated / mock 等，retrieved/inferred 不可当事实。
- 延迟键固定为 `perceive_ms` / `knowledge_ms` / `slow_ms` / `bridge_ms` / `fast_ms` / `execute_ms`。

```bash
curl "http://127.0.0.1:8000/api/episode/ep-win/steps"
```

```json
{
  "id": "ep-win",
  "found": true,
  "step_count": 10,
  "steps": [
    { "step": 1, "elapsed_sec": 1.0, "cost": 15, "life": 3,
      "state_text": "当前费用15……",
      "plan": { "actions": [ ... ] },
      "decision_summary": "部署先锋回费",
      "decision_analysis": ["费用充足，先下先锋"],
      "evidence": [ { "level": "fact", "source": "PRTS" } ],
      "step_reward": 0.0,
      "latency_ms": { "perceive_ms": 1.2, "knowledge_ms": 0.5, "slow_ms": 12.3,
                      "bridge_ms": 0.3, "fast_ms": 0.2, "execute_ms": 0.8 },
      "trace": {
        "step": 1, "state_excerpt": "当前费用15……",
        "knowledge": { "citations": [ { "source": "PRTS", "evidence": "fact",
                                        "detail": "…", "url": "", "score": null } ] },
        "decision": { "reasoning": { "summary": "部署先锋回费", "analysis": [ ... ] },
                      "confidence": 0.8, "knowledge_used": [ ... ] },
        "bridge": { "source": "mock", "hint": "…" },
        "command": { "reactor": "mock", "plan": { ... }, "dropped": [ ... ] },
        "execute": { "total": 1, "succeeded": 1, "failed": 0 },
        "reflection": { "verdict": "good", "issues": [], "adjustment": "" },
        "latency_ms": { "perceive_ms": 1.2, "slow_ms": 12.3 } } }
  ]
}
```

---

## 三、知识图谱

只读访问本地 NetworkX 图谱（`data/graph/arknights_graph.graphml`）。
节点 id 形如 `operator:能天使`、`enemy:碎骨`、`stage:3-8`、`skill:过载模式`；
边关系：`HAS_SKILL`、`CONTAINS_ENEMY`(fact)、`COUNTERS`、`RECOMMENDS`(inferred)。

### GET `/api/graph/overview`

节点 / 边规模统计。

```bash
curl "http://127.0.0.1:8000/api/graph/overview"
```

```json
{
  "found": true,
  "evidence": "fact",
  "node_kinds": { "operator": 460, "enemy": 1816, "stage": 487, "skill": 1005 },
  "edge_relations": { "COUNTERS": 139461, "HAS_SKILL": 1005,
                      "CONTAINS_ENEMY": 2332, "RECOMMENDS": 76795 },
  "total_nodes": 3768,
  "total_edges": 219593
}
```

### GET `/api/graph/node/{node_id}`

节点属性 + 全部有向邻居（含 `relation` 与 `direction=in/out`）。
超密节点（如高星干员经 COUNTERS 推断可达数百邻居）最多返回 200 条，
并用 `neighbors_truncated=true` 标记。

```bash
curl "http://127.0.0.1:8000/api/graph/node/operator:能天使"
```

```json
{
  "found": true,
  "evidence": "fact",
  "node_id": "operator:能天使",
  "attrs": { "kind": "operator", "name": "能天使", "class": "狙击", "star": 6 },
  "neighbor_count": 773,
  "neighbors_shown": 200,
  "neighbors_truncated": true,
  "neighbors": [
    { "node_id": "skill:过载模式", "relation": "HAS_SKILL",
      "direction": "out", "kind": "skill", "name": "过载模式" }
  ]
}
```

### GET `/api/graph/subgraph/{stage_id}`

某关卡的子图：关卡节点 + `CONTAINS_ENEMY` 敌人 + `RECOMMENDS` 推荐干员（上限 50，
超出置 `operators_truncated=true`）。

```bash
curl "http://127.0.0.1:8000/api/graph/subgraph/3-8"
```

```json
{
  "found": true,
  "evidence": "fact",
  "stage_id": "3-8",
  "stage_title": "3-8 黄昏",
  "enemy_count": 8,
  "operator_count": 0,
  "nodes": [ { "node_id": "stage:3-8", "kind": "stage", "name": "黄昏" },
             { "node_id": "enemy:碎骨", "kind": "enemy", "name": "碎骨" } ],
  "edges": [ { "source": "stage:3-8", "target": "enemy:妖怪",
               "relation": "CONTAINS_ENEMY", "count": "16", "evidence": "fact" } ]
}
```

> 说明：部分关卡（如 3-8 的 boss 碎骨无类型弱点）可能没有 RECOMMENDS 边，
> 此时 `operator_count=0` 属正常结果，不是错误。

---

## 四、Dashboard 专属接口（dashboard_design.md §3）

CPU 侧全部可落地：`source-stone` 包真实计算；`account/progress/tasks/live` 用 mock/空态；
`training` 留 V100 骨架。所有 wire 格式 **snake_case**，与 `frontend/src/types/index.ts` 对齐；
前端经 `deepCamelize` 转 camelCase 后消费。

### GET `/api/health`（扩展，§3.6）

模块在线状态/延迟 + 显存 + 环境。CPU 侧 modules 静态声明为 mock 全在线、`latency_ms_p50=null`
（不造假数字）；vram 无 GPU 时全 null。V100/真机阶段替换为真实采集（nvidia-smi / 各模块计时）。

**响应示例：**
```json
{
  "status": "ok",
  "env": "mock",
  "server_version": "0.2.0",
  "ts": "2026-09-26T21:28:39+08:00",
  "modules": {
    "perception":      {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "agent_slow":      {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "agent_fast":      {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "vlm":             {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "knowledge_rag":   {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "knowledge_graph": {"online": true, "evidence": "fact", "latency_ms_p50": null},
    "action":          {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "env":             {"online": true, "evidence": "mock", "latency_ms_p50": null}
  },
  "vram": {"used_mb": null, "total_mb": null, "util": null},
  "live_subscribers": 0
}
```

### GET `/api/resources/source-stone`（§3.3，真实计算）

源石首通获取三档（立即可拿/短期/长期）。直接包 `knowledge.source_stone_tracker.SourceStoneTracker`，
从 `data/prts_raw/stages/` 读主线关卡表。分档为窗口估算（evidence: **inferred**），非账号实测。

**查询参数：**
| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `completed_normal` | string | None | 已通关普通关，逗号分隔，如 `1-1,1-2,3-8` |
| `completed_raid` | string | None | 已通关突袭关，逗号分隔 |
| `current_stone` | int | 0 | 当前持有源石数（0=未知） |
| `short_term_window` | int | 6 | 短期可拿窗口关数 |

**响应：** `SourceStoneReport.to_dict()`，关键字段：
`current_stone` / `total_remaining` / `prompt_decision_stone`（仅立即+短期，喂抽卡决策）/
`long_term_stone`（仅规划，不进决策）/ `tiers.{immediate,short_term,long_term}`（各含
`normal_stone`/`raid_stone`/`stages`）/ `progress` / `remaining_stages`。

**错误：** `503` — PRTS 关卡数据缺失（需先跑 `scripts/crawl_prts.sh`）。

### GET `/api/resources/account`（§3.3，mock）

合成玉/至纯源石/龙门币/干员数。真机阶段由 `perception/gacha.py`/`shop.py` 解析 + 账号态存储提供；
CPU 侧返回 mock 数据，带 `evidence:"mock"`。

**响应示例：** `{"orundum": 12000, "originite": 18, "lmd": 1250000, "operator_count": 168, "evidence": "mock"}`

### GET `/api/resources/progress`（§3.3，mock）

主线关卡进度。真机阶段由 episode 结算 + PRTS 关卡台账推算；CPU 侧 mock。

**响应示例：** `{"cleared": 0, "total": 288, "current_chapter": "0-1", "evidence": "mock"}`

### GET `/api/tasks`（§3.4，空队列）

任务队列（当前任务 + 排队中下一步）。任务编排系统待接入；CPU 侧返回空队列。

**响应示例：**
```json
{
  "current": null,
  "upcoming": [],
  "evidence": "mock",
  "note": "任务编排系统未接入；当前返回空队列。decision_loop 步骤视图待后续接入。"
}
```

### GET `/api/live/snapshot`（§3.2，HTTP 轮询降级）

取最新一帧（GameState + VLM 分析 + DecisionFlow + 六段延迟）。从 `api.live_state.LiveState`
内存存储取；无真实 env 跑局时返回默认 mock 帧（与 `frontend/public/mock/live.json` 同 schema）。

**响应顶层字段：** `connected` / `episode_id` / `screenshot_data_url` / `state`（含
`cost`/`available_operators`/`skill_cooldowns`/`enemies`/`deployable_grids`）/ `vlm`（含
`situation`/`strategic_advice`/`confidence`/`evidence[]`）/ `decision_flow[]`（每步含
`step`/`reasoning`/`action`/`confidence`/`knowledge_used[]`/`latency_ms`）/ `latency_ms`
（capture/cv/retrieval/llm/action/total）/ `ts`。

> 截图属游戏画面，**只在本机内存/本地网络流转，不落库不入 git**；mock 帧 `screenshot_data_url=null`。

### WS `/ws/live`（§3.2，增量推送）

实时对局 WebSocket。连接后**先发最新帧**，之后每收到新帧就推送（JSON 帧，结构同
`/api/live/snapshot`）。前端 `USE_MOCK=false` 时订阅此通道；HTTP snapshot 作降级。

- 后端 `LiveState` 维护订阅者队列（每连接一个 `asyncio.Queue(maxsize=16)`，满则丢最旧保最新）。
- `ArknightsEnv` 跑局时每步调用 `app.state.live_state.push(frame)` 发布新帧（TODO-V100/真机接入）。
- 连接断开自动 unsubscribe。

### GET `/api/training/runs`（§3.5，V100 骨架）

训练 run 列表（元数据：base_model / LoRA 配置 / status / current_step / total_steps / eval）。
V100 上线后读 `results/` 下 trainer 落盘文件；CPU 侧 `connected:false`、`runs:[]`。

**响应示例：**
```json
{"connected": false, "runs": [], "evidence": "mock",
 "note": "V100 未接入（TODO-V100）；训练 metrics 由 trainer 落 results/metrics.jsonl 后提供。"}
```

### GET `/api/training/metrics`（§3.5，V100 骨架）

某个 run 的 metrics 时间序列（`step`/`train_loss`/`eval_loss`/`lr`）。V100 上线后读
`results/<run>/metrics.jsonl`；CPU 侧返回 **409** 空态。

**查询参数：** `run`（string，必填，run id）。

**响应（409）：** `{"found": false, "evidence": "mock", "run": "<id>", "metrics": [], "message": "V100 未接入..."}`

---

## 五、给前端的建议

- 一律先判 `found`；`evidence=inferred/retrieved` 的内容要以"参考 / 推断"样式展示，
  不要渲染成确定事实。
- 名称、关卡编号在 URL 中需做 `encodeURIComponent`（含中文 / 括号 / 冒号）。
- 图谱首查较慢（加载 graphml），前端可在启动后先请求一次 `/api/graph/overview` 预热。
- Dashboard 六模块全部走 `VITE_USE_MOCK` 切换：默认读 `frontend/public/mock/*.json`，
  设 `false` 时请求同源 `/api/*`（dev 经 vite proxy 到 `:8000`）。mock 与真实接口 schema 一致，
  切换无需改组件。
