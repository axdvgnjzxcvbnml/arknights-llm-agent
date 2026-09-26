# Type Hints 覆盖率状态

> 审计时间：2026-09-27
> 范围：agent/ knowledge/ perception/ action/ env/ api/ training/ strategy/ video_extract/

## 一、覆盖率总览

| 模块 | 公开接口数 | 有 type hints | 覆盖率 | 评级 |
| --- | --- | --- | --- | --- |
| agent/ | 12 | 10 | 83% | 绿 |
| env/ | 8 | 7 | 88% | 绿 |
| action/ | 10 | 8 | 80% | 绿 |
| perception/ | 15 | 11 | 73% | 黄 |
| knowledge/ | 20 | 14 | 70% | 黄 |
| api/ | 17 | 17 | 100% | 绿 |
| training/ | 12 | 8 | 67% | 黄 |
| strategy/ | 5 | 4 | 80% | 绿 |
| video_extract/ | 10 | 7 | 70% | 黄 |
| **合计** | **109** | **86** | **79%** | **黄** |

## 二、已覆盖的核心接口

### agent/
- `SlowThinker.think(state, knowledge, history) -> AgentDecision`
- `FastReactor.react(decision, state) -> ActionPlan`
- `LatentBridge.project(decision) -> dict`
- `DecisionLoop.run(max_steps) -> List[StepRecord]`
- `MCPKnowledge.query(query, tools) -> List[ToolResult]`

### env/
- `ArknightsEnv.reset() -> GameState`
- `ArknightsEnv.step(action) -> Tuple[GameState, float, bool, dict]`
- `ArknightsEnv.run_episode(max_steps) -> EpisodeLog`
- `EpisodeStore.save(episode) -> str`
- `EpisodeStore.load(episode_id) -> Optional[EpisodeLog]`

### api/
- 所有 FastAPI 路由函数均有 Pydantic 入参/返回类型（100% 覆盖）

## 三、缺口清单（优先级排序）

### 高优先级（公开接口缺 hints）
1. `knowledge/rag/retriever.py: retrieve(query, k, doc_type) -> List[Chunk]` — 返回类型未标注
2. `knowledge/graph/query_graph.py: query(node_id, relation) -> List[dict]` — 返回类型未标注
3. `perception/state_parser.py: parse(screenshot, detections) -> GameState` — 入参类型未标注
4. `training/sft_data_prep.py: build_examples(job, ...) -> Tuple[List[dict], dict]` — 返回 tuple 未标注元素类型

### 中优先级（内部函数缺 hints）
5. `knowledge/rag/build_rag.py: chunk_operator(data, max_chars, source) -> List[dict]`
6. `knowledge/graph/build_graph.py: derive_counter_rules(enemy, rules_cfg) -> List[tuple]`
7. `perception/state_to_text.py: render(state, vlm) -> str`

### 低优先级（私有工具函数）
8. 各模块的 `_to_float`、`_kv_line`、`_loc_text` 等私有函数

## 四、改进建议

1. **短期**：补高优先级 4 个公开接口的 type hints（工作量约 30 分钟）
2. **中期**：配置 mypy 或 pyright，CI 跑类型检查（仅检查公开接口）
3. **长期**：目标公开接口覆盖率 100%，内部函数覆盖率 80%+
4. **Pydantic 模型**：所有数据结构（GameState/ActionPlan/AgentDecision）已有完整 type hints，是好的基础

## 五、已知限制

- Python 3.8 不支持 `list[int]` 语法，需用 `List[int]`（项目已统一 `from __future__ import annotations`）
- Mock 类的 type hints 与真实类一致，通过 ABC 基类约束
- 动态加载的模块（MCP 工具注册）无法静态检查
