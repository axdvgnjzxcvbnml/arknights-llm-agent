# mcp_tools —— 知识库 MCP 工具层

把本地 PRTS JSON、知识图谱（NetworkX）、RAG（bge + ChromaDB）封装成 6 个结构化工具，
既可经 **MCP 协议**（stdio）暴露给 LLM，也可在 Agent 进程内直接 import 调用。

## 分层

| 文件 | 职责 | 是否 import mcp |
|---|---|---|
| `schemas.py` | 全部输入/输出的 Pydantic 契约、`evidence` 枚举、推断警示语 | 否 |
| `service.py` | `KnowledgeService` 业务层：实体解析 + 6 查询；图谱/向量库**懒加载** | 否 |
| `tools_operator.py` | `query_operator` / `query_skill` | 否 |
| `tools_enemy.py` | `query_enemy` | 否 |
| `tools_stage.py` | `query_stage` / `recommend_operators` | 否 |
| `tools_guide.py` | `search_guide` | 否 |
| `server.py` | FastMCP 注册 6 工具，`python -m knowledge.mcp_tools.server` 启动 stdio | 是 |

工具薄封装不依赖 `mcp`、chromadb、networkx（重资源在 `service.py` 方法内延迟导入），
因此 `import knowledge.mcp_tools` 很轻，单元测试与 CI 不会被模型/向量库拖挂。

## 工具一览

| 工具 | 参数 | 数据源 | evidence |
|---|---|---|---|
| `query_operator` | `name` | PRTS 干员 JSON（meta/trait/属性/技能） | fact |
| `query_skill` | `operator`, `skill_name` | PRTS 干员 JSON，技能名精确优先+包含兜底 | fact |
| `query_enemy` | `name`, `level?` | PRTS 敌人 JSON，按级别返回 | fact |
| `query_stage` | `stage_id` | PRTS 关卡 JSON（信息卡+敌情表） | fact |
| `search_guide` | `query`, `k=5`, `doc_type?` | RAG：bge-small-zh-v1.5 + ChromaDB | **retrieved**（参考资料） |
| `recommend_operators` | `stage_id`, `constraints?` | 知识图谱 COUNTERS→RECOMMENDS 规则 | **inferred** |

`constraints` 支持：`classes`（职业白名单）、`min_star`/`max_star`（1–6）、
`top_n`（1–30，默认 8）、`exclude_operators`（排除名单）。

## evidence 规则（重要）

- 干员/技能/敌人/关卡信息解析自 PRTS Wiki，标 `fact`。
- `search_guide` 标 **`retrieved`**：RAG 返回的是"检索到的相关文档"（参考资料），不是
  事实判断。片段内容虽来自 PRTS，但是否与当前局势相关、能否采信要由 LLM 结合上下文核实，
  响应 `note` 会明确提示，不能直接当确定事实陈述。
- `recommend_operators` 由规则推断（干员按防/抗/速阈值克制敌人，再聚合到关卡），
  响应与每个推荐项都恒为 `inferred`（`RecommendOut` 在类型层强制默认 inferred），
  并携带中文警示 `note`，防止 LLM 把推断当官方事实。
- 关卡敌人未达克制阈值时（如 3-8），返回 `found=true` 但 `operators=[]` 且附说明，
  与"关卡不存在"（`found=false`）区分开。

## 启动 MCP 服务（stdio）

```bash
python -m knowledge.mcp_tools.server
```

MCP 客户端配置：`command=python`，`args=["-m","knowledge.mcp_tools.server"]`。
列工具自检：`mcp.list_tools()` 返回 6 个工具及其 input schema。

## 与社区 PRTS MCP Server 的关系

参考了社区 `3aKHP/prts-mcp`（MIT）的参数命名风格（`name` / `stage_id` / `k`）与查询粒度；
其数据源为 ArknightsGameData 游戏表，本项目数据源为**自建爬虫 JSON + RAG + 知识图谱**，
实现独立。社区版没有独立技能查询与干员推荐，`query_skill`、`recommend_operators`
是本项目基于知识图谱的差异化扩展。

## 数据依赖

- `data/prts_raw/{operators,enemies,stages}/*.json`：爬虫产物（已 gitignore）
- `data/graph/arknights_graph.graphml`：图谱产物（已 gitignore）
- `data/vector_store/`：ChromaDB 持久化目录（已 gitignore）

数据缺失时各工具返回 `found=false` 与说明，不抛异常。

## 测试

```bash
python -m pytest tests/test_mcp_tools.py -v
```

三层：契约/边界用例恒跑（不依赖数据与模型）；真实数据、图谱、向量库用例在对应产物
缺失时自动 skip。当前语料 24 个用例全部通过。
