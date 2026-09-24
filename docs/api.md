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
落库方式：

```python
from api.server import EpisodeStore
EpisodeStore().save("ep-win", episode_log.model_dump())   # episode_log 来自 env.run_episode()
```

### GET `/api/episode/{id}`

返回一局摘要。`id` 仅允许字母数字 `_ -`。

```bash
curl "http://127.0.0.1:8000/api/episode/ep-win"
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
  "reward": { "total": 87.0, "items": [ ... ] },
  "episode": { "stage_id": "3-8", "outcome": "win", "steps": [ ... ] }
}
```

### GET `/api/episode/{id}/steps`

返回逐步明细：每步状态文本、动作 plan、决策理由（`decision_analysis`）、
证据（`evidence`）、单步奖励、各阶段延迟（`latency_ms`）。

```bash
curl "http://127.0.0.1:8000/api/episode/ep-win/steps"
```

```json
{
  "id": "ep-win",
  "found": true,
  "step_count": 10,
  "steps": [
    { "step": 0, "elapsed_sec": 1.0, "cost": 15, "life": 3,
      "state_text": "当前费用15……",
      "plan": { "actions": [ ... ] },
      "decision_summary": "部署先锋回费",
      "decision_analysis": ["费用充足，先下先锋"],
      "evidence": ["fact:PRTS"],
      "step_reward": 0.0,
      "latency_ms": { "perceive": 1.2, "slow": 12.3, "act": 0.8 } }
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

## 四、其它

### GET `/api/health`

存活探针，返回 `{"status":"ok",...}`。

## 给前端的建议

- 一律先判 `found`；`evidence=inferred/retrieved` 的内容要以"参考 / 推断"样式展示，
  不要渲染成确定事实。
- 名称、关卡编号在 URL 中需做 `encodeURIComponent`（含中文 / 括号 / 冒号）。
- 图谱首查较慢（加载 graphml），前端可在启动后先请求一次 `/api/graph/overview` 预热。
