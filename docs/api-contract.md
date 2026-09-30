# API 契约

> 版本：v1.0
> 最后更新：2026-09-30
> 状态：冻结，任何改动必须走 PR + 版本号升级
> OpenAPI schema：`docs/openapi.yaml`
> 契约测试：`tests/test_api_contract.py`

---

## 一、概述

### 1.1 Base URL

```
http://<host>:8000/api/v1
```

> 当前实现使用 `/api/` 前缀（无版本号），v1.0 冻结后将迁移到 `/api/v1/`。迁移期间 `/api/` 保持兼容。

### 1.2 通用响应格式

所有接口返回 JSON，包含以下通用字段（如适用）：

```json
{
  "found": true,
  "message": "",
  "evidence": "fact|retrieved|inferred|estimated|unknown|mock",
  "source_url": "https://prts.wiki/w/...",
  "...": "具体数据字段"
}
```

### 1.3 Evidence 分级

| evidence | 含义 | 颜色 |
|----------|------|------|
| `fact` | 来自 PRTS 的确定数值 | 绿色实线 |
| `annotated` | 人工标注/验证 | 蓝色实线 |
| `cv` | 计算机视觉检测结果 | 青色实线 |
| `retrieved` | 检索到的相关文档（非事实判断） | 橙色虚线 |
| `inferred` | 模型推断/规则推导 | 紫色虚线 |
| `estimated` | 估算值（非精确测量） | 黄色虚线 |
| `mock` | mock 数据（非真实） | 灰色虚线 |
| `unknown` | 无法确定 | 红色 |

### 1.4 状态码

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误（如干员名不存在） |
| 404 | 资源不存在 |
| 409 | 冲突/空态（如训练数据未就绪） |
| 500 | 服务器内部错误 |

---

## 二、知识接口（7 个）

### 2.1 GET /api/operator/{name}

查询干员完整信息（meta + 技能 + 特性）。

**参数：**
- `name` (path, string, required): 干员名称（中文，URL 编码）

**响应：**
```json
{
  "found": true,
  "evidence": "fact",
  "source_url": "https://prts.wiki/w/能天使",
  "name": "能天使",
  "display_name": "能天使",
  "star_rating": 6,
  "class": "狙击",
  "branch": "速射手",
  "traits": {"desc": "..."},
  "skills": [{"name": "过载模式", "level": 7, "...": "..."}],
  "meta": {"...": "..."}
}
```

**错误：** 400 — 干员不存在

---

### 2.2 GET /api/skill/{operator}/{skill_name}

查询技能详情。

**参数：**
- `operator` (path, string, required): 干员名称
- `skill_name` (path, string, required): 技能名称

**响应：**
```json
{
  "found": true,
  "evidence": "fact",
  "operator": "能天使",
  "skill_name": "过载模式",
  "level": 7,
  "sp_cost": 25,
  "initial_sp": 10,
  "duration": 25,
  "description": "攻击力提升..."
}
```

**错误：** 400 — 干员或技能不存在

---

### 2.3 GET /api/enemy/{name}

查询敌人属性（按级别）。

**参数：**
- `name` (path, string, required): 敌人名称

**响应：**
```json
{
  "found": true,
  "evidence": "fact",
  "name": "碎骨",
  "levels": [
    {"level": 0, "hp": 2500, "atk": 300, "def": 200, "magic_resist": 0, "...": "..."},
    {"level": 1, "...": "..."},
    {"level": 2, "...": "..."}
  ]
}
```

**错误：** 400 — 敌人不存在

---

### 2.4 GET /api/stage/{stage_id}

查询关卡信息和敌情。

**参数：**
- `stage_id` (path, string, required): 关卡 ID（如 "3-8"）

**响应：**
```json
{
  "found": true,
  "evidence": "fact",
  "stage_id": "3-8",
  "name": "3-8 行动",
  "difficulty": "普通",
  "enemies": [{"name": "碎骨", "count": 1, "...": "..."}],
  "map": {"cols": 10, "rows": 8, "...": "..."},
  "spawn_plan": [{"wave": 1, "enemies": [...], "estimated_time": 5.0}]
}
```

**错误：** 400 — 关卡不存在

---

### 2.5 GET /api/search

RAG 混合检索（向量 + BM25 + RRF 融合）。

**参数：**
- `q` (query, string, required): 检索查询
- `k` (query, int, optional, default=5): 返回结果数
- `doc_type` (query, string, optional): 按类型过滤（operator/enemy/stage/guide）

**响应：**
```json
{
  "query": "能天使的技能是什么",
  "hits": [
    {
      "content": "能天使的技能包括：冲锋模式、扫射模式、过载模式...",
      "score": 0.85,
      "source": "能天使",
      "type": "operator",
      "section": "skills",
      "url": "https://prts.wiki/w/能天使",
      "evidence": "retrieved"
    }
  ]
}
```

> 注意：hit 字段平铺（无 metadata 嵌套），无 total 字段。

---

### 2.6 GET /api/recommend/{stage_id}

推荐干员组合（基于知识图谱 + MAA 统计先验）。

**参数：**
- `stage_id` (path, string, required): 关卡 ID
- `constraints` (query, string, optional): 约束条件（JSON 字符串，如 `{"max_cost": 10, "classes": ["先锋","狙击"]}`）

**响应：**
```json
{
  "found": true,
  "evidence": "inferred",
  "stage_id": "3-8",
  "operators": [
    {"name": "能天使", "role": "输出", "reason": "对空高速狙击，适合处理飞行敌人"},
    {"name": "星熊", "role": "阻挡", "reason": "高防御重装，可阻挡碎骨"}
  ],
  "note": "推荐基于知识图谱规则推导和MAA作业统计先验，非最优解"
}
```

> 注意：`recommend_operators` 的 COUNTERS 和 RECOMMENDS 边必须标 `inferred`，避免 LLM 把推断当事实。

---

## 三、对局接口（3 个）

### 3.1 GET /api/episodes

对局列表。

**响应：**
```json
{
  "found": true,
  "count": 2,
  "episodes": [
    {"id": "mock-3-8-win", "title": "3-8 通关", "stage_id": "3-8", "outcome": "win", "step_count": 10}
  ]
}
```

---

### 3.2 GET /api/episode/{episode_id}

对局报告（汇总 + 奖励 + 地图）。

**参数：**
- `episode_id` (path, string, required)

**响应：**
```json
{
  "id": "mock-3-8-win",
  "stage_id": "3-8",
  "outcome": "win",
  "step_count": 10,
  "duration_sec": 120,
  "reward": {
    "total": 85,
    "win_bonus": 100,
    "leak_penalty": -10,
    "overcost_penalty": -5,
    "summary_line": "通关 +100，漏怪 -10，费用溢出 -5 = 85"
  },
  "totals": {"actions_total": 15, "actions_succeeded": 14, "avg_confidence": 0.82},
  "map": {"cols": 10, "rows": 8, "cells": [...]}
}
```

---

### 3.3 GET /api/episode/{episode_id}/steps

每步详情（状态 + 决策 + 动作 + 结果 + evidence）。

**参数：**
- `episode_id` (path, string, required)

**响应：**
```json
[
  {
    "step": 1,
    "elapsed_sec": 5.0,
    "state": {"cost": 12, "life_points": 20, "deployed": [...], "enemies_on_field": [...]},
    "knowledge": {"query": "3-8敌情", "context_text": "...", "citations": [...]},
    "reasoning": {"summary": "...", "analysis": [...], "considered_actions": [...]},
    "decision": {"confidence": 0.85, "plan": {"actions": [...]}},
    "execute": {"success": true, "duration_ms": 120},
    "after": {"cost": 7, "life": 20},
    "evidence": [{"level": "fact", "source": "PRTS"}, {"level": "inferred", "source": "规则推导"}],
    "latency_ms": {"perception": 15, "knowledge": 45, "think": 1500, "execute": 120}
  }
]
```

> 注意：EpisodeLog（EnvStep）和 DecisionLog（StepRecord）已合流，steps 返回完整可解释数据。

---

## 四、知识图谱接口（3 个）

### 4.1 GET /api/graph/overview

图谱概览（节点和边的统计）。

**响应：**
```json
{
  "found": true,
  "evidence": "fact",
  "node_kinds": {"operator": 460, "skill": 1005, "stage": 487, "enemy": 1816},
  "edge_relations": {"COUNTERS": 139461, "HAS_SKILL": 1005, "CONTAINS_ENEMY": 2332, "RECOMMENDS": 76795},
  "total_nodes": 3768,
  "total_edges": 219593,
  "note": "..."
}
```

---

### 4.2 GET /api/graph/node/{node_id}

节点详情和邻居。

**参数：**
- `node_id` (path, string, required): 节点 ID（页面标题）

**响应：**
```json
{
  "found": true,
  "node": {"id": "能天使", "type": "operator", "attributes": {...}},
  "neighbors": [
    {"id": "过载模式", "type": "skill", "relation": "HAS_SKILL", "direction": "out"},
    {"id": "碎骨", "type": "enemy", "relation": "COUNTERS", "direction": "out", "evidence": "inferred"}
  ]
}
```

> 待办：节点邻居查询改分组配额，另加反向"推荐关卡"接口（合并后统一处理）。

---

### 4.3 GET /api/graph/subgraph/{stage_id}

某个关卡的子图（关卡 + 敌人 + 推荐干员）。

**参数：**
- `stage_id` (path, string, required)

**响应：**
```json
{
  "found": true,
  "stage_id": "3-8",
  "nodes": [{"id": "3-8", "type": "stage"}, {"id": "碎骨", "type": "enemy"}, {"id": "能天使", "type": "operator"}],
  "edges": [{"source": "3-8", "target": "碎骨", "relation": "CONTAINS"}, {"source": "3-8", "target": "能天使", "relation": "RECOMMENDS", "evidence": "inferred"}]
}
```

---

## 五、资源接口（3 个）

### 5.1 GET /api/resources/source-stone

源石三档（立即可拿 / 短期可拿 / 长期可拿）。

**响应：**
```json
{
  "found": true,
  "evidence": "fact",
  "tiers": {
    "immediate": {"normal_stone": 1, "raid_stone": 0, "stages": [{"stage_id": "0-1", "kind": "normal", "stone": 1}]},
    "short_term": {"normal_stone": 6, "raid_stone": 7, "stages": [...]},
    "long_term": {"normal_stone": 281, "raid_stone": 98, "stages": [...]}
  },
  "short_term_window": 6,
  "progress": {"earned_normal": 0, "remaining_normal": 288, "earned_raid": 0, "remaining_raid": 105},
  "total_remaining": 393
}
```

> 注意：三档结构在 `tiers` 下（immediate/short_term/long_term），不是顶层字段。抽卡决策 Prompt 只看前两档（immediate + short_term），不看 long_term。

---

### 5.2 GET /api/resources/account

账户资源（合成玉 / 龙门币 / 干员数）。

**响应：**
```json
{
  "found": true,
  "evidence": "mock",
  "synthetic_jade": 18000,
  "lungmen_dollar": 500000,
  "operator_count": 120,
  "note": "mock 数据，待接游戏内数据"
}
```

---

### 5.3 GET /api/resources/progress

关卡进度。

**响应：**
```json
{
  "found": true,
  "evidence": "mock",
  "main_stages": {"total": 487, "cleared": 200, "three_star": 150},
  "event_stages": {"total": 200, "cleared": 50},
  "note": "mock 数据，待接游戏内数据"
}
```

---

## 六、任务接口（1 个）

### 6.1 GET /api/tasks

任务队列（当前在做什么、下一步计划）。

**响应：**
```json
{
  "found": true,
  "current": {"type": "decision_loop", "step": 5, "stage_id": "3-8"},
  "upcoming": [{"type": "next_decision", "eta_ms": 2000}],
  "evidence": "mock",
  "note": "任务编排系统未接入；当前返回空队列。"
}
```

---

## 七、实时对局接口（2 个）

### 7.1 GET /api/live/snapshot

HTTP 初始快照（从 ArknightsEnv 的内存状态推一帧）。

**响应：**
```json
{
  "found": true,
  "evidence": "mock",
  "connected": true,
  "episode_id": "EP-MOCK-0001",
  "ts": 1234567890,
  "state": {"cost": 15, "life_points": 20, "deployed": [...], "enemies_on_field": [...]},
  "decision": {"confidence": 0.85, "plan": {"actions": [...]}},
  "vlm": {"situation": "...", "strategic_advice": "...", "confidence": 0.8},
  "latency_ms": {...}
}
```

> 注意：时间戳字段是 `ts`（不是 timestamp）。

---

### 7.2 WS /ws/live

WebSocket 增量推送（帧 + 状态 + DecisionLog）。

**消息格式：**
```json
{
  "type": "frame|state|decision|log",
  "timestamp": 1234567890,
  "data": {"...": "..."}
}
```

> 注意：HTTP snapshot 作降级，WS 未接通时前端用轮询（usePolling）。

---

## 八、训练接口（2 个）

### 8.1 GET /api/training/runs

训练 run 列表（元数据）。

**响应：**
```json
{
  "found": true,
  "connected": false,
  "runs": [],
  "note": "V100 上线后接真实数据，读 results/metrics.jsonl"
}
```

---

### 8.2 GET /api/training/metrics

某个 run 的 metrics 时间序列。

**参数：**
- `run` (query, string, required): run ID

**响应（CPU 侧空态）：**
```json
{
  "found": false,
  "error": "training data not available",
  "note": "V100 上线后接真实数据",
  "metrics": []
}
```

**状态码：** 409 — 训练数据未就绪（CPU 侧预期行为）

---

## 九、系统接口（1 个）

### 9.1 GET /api/health

系统健康检查（模块状态 + 延迟 + 显存）。

**响应：**
```json
{
  "status": "ok",
  "env": "mock",
  "server_version": "0.2.0",
  "ts": "2026-09-30T12:00:00+08:00",
  "modules": {
    "perception": {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "agent_slow": {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "knowledge_rag": {"online": true, "evidence": "mock", "latency_ms_p50": null},
    "knowledge_graph": {"online": true, "evidence": "fact", "latency_ms_p50": null}
  },
  "vram": {"used_mb": null, "total_mb": null, "util": null},
  "live_subscribers": 0
}
```

---

## 十、变更日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-30 | 初始冻结，21 个接口（20 HTTP + 1 WS） |

---

## 十一、待办

- [ ] 迁移到 `/api/v1/` 前缀（当前 `/api/` 兼容）
- [ ] 节点邻居查询改分组配额 + 反向"推荐关卡"接口
- [ ] `/api/resources/account` 和 `/api/resources/progress` 接真实数据
- [ ] `/api/training/runs` 和 `/api/training/metrics` V100 上线后接真实数据
- [ ] OpenAPI schema 自动生成（当前手写）
