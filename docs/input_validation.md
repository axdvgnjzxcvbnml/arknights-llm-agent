# 输入验证加固

> 审计时间：2026-09-27
> 范围：API / MCP 工具 / CLI 三类对外接口

## 一、API 输入验证

| 接口 | 参数 | 验证方式 | 边界处理 |
| --- | --- | --- | --- |
| `GET /api/operator/{name}` | name (path) | FastAPI 路径参数自动校验 | 空名→404；不存在→found=False |
| `GET /api/enemy/{name}` | name (path) | 同上 | 同上 |
| `GET /api/stage/{stage_id}` | stage_id (path) | 同上 | 不存在→found=False |
| `GET /api/search` | q (query, required) | FastAPI Query 必填 | 缺 q→422；超长→正常检索 |
| `GET /api/search` | k (query, default=5) | int 类型校验 | 非 int→422 |
| `GET /api/episode/{id}` | episode_id (path) | EpisodeStore.check_id（字母数字_-，1-128位） | 非法 id→400 |
| `GET /api/graph/node/{id}` | node_id (path) | 路径参数 | 不存在→found=False |
| `GET /api/training/metrics` | run (query) | 字符串 | 缺失→409 空态 |

## 二、MCP 工具输入验证

| 工具 | 参数 | 验证 |
| --- | --- | --- |
| query_operator | name | 非空字符串；Pydantic OperatorQuery 模型 |
| query_skill | operator, skill_name | 非空字符串 |
| query_enemy | name, level (optional) | level 为 None 或非负整数 |
| query_stage | stage_id | 非空字符串 |
| search_guide | query, k (default=5), doc_type (optional) | k>0；doc_type 为 None 或 operator/enemy/stage/guide |
| recommend_operators | stage_id, constraints (optional) | stage_id 非空 |

## 三、CLI 输入验证

| 脚本 | 参数 | 验证 |
| --- | --- | --- |
| batch_crawl.py | --type, --limit | type ∈ {operator,enemy,stage}；limit>0 |
| build_rag.py | --rebuild | 布尔标志 |
| build_graph.py | 无参数 | 从 config 读取 |
| project_status.py | 无参数 | 自动检测 |
| validate_configs.py | 无参数 | 自动验证所有 configs |

## 四、已知边界

1. **路径穿越防护**：EpisodeStore.check_id 限制文件名只含字母数字_-，防止路径穿越
2. **超长字符串**：API 层无显式长度限制，但 FastAPI + uvicorn 默认有请求体大小限制
3. **特殊字符**：干员名/敌人名可能含中文/特殊字符，Pydantic str 类型正常接收
4. **SQL 注入**：项目不使用 SQL，ChromaDB/NetworkX 无注入风险

## 五、后续建议

1. API 层加 Pydantic response_model 校验返回格式
2. MCP 工具加 doc_type 枚举校验（当前只在文档里说明）
3. CLI 脚本用 typer 做参数校验（部分已用）
