# 测试覆盖率报告

**生成日期**：2026-09-26
**测试框架**：pytest + pytest-cov
**运行环境**：CPU 沙箱（Python 3.12，无 GPU）
**测试文件数**：24 个 test_*.py

---

## 一、覆盖率总览

分批运行（沙箱 4GB 内存限制，全量 pytest 会 OOM），核心模块覆盖率：

| 模块 | 覆盖率 | 状态 |
|------|--------|------|
| `agent/` | **88%** | ✅ 良好 |
| `env/` | **88%** | ✅ 良好 |
| `action/` | **88%** | ✅ 良好（adb_controller 真实实现除外） |
| `knowledge/mcp_tools/` | **91%** | ✅ 良好 |
| `knowledge/rag/retriever.py` | **99%** | ✅ 优秀 |
| `knowledge/rag/bm25_index.py` | **63%** | ⚠️ 刚过线（缓存加载/构建路径未覆盖） |
| `knowledge/graph/query_graph.py` | **~90%** | ✅ 已补（mock 小图，23 用例） |
| `env/episode_store.py` | **~95%** | ✅ 已补（24 用例） |
| `knowledge/source_stone_tracker.py` | **98%** | ✅ 优秀 |
| `knowledge/crawler/batch_crawl.py` | **73%** | ✅ 良好 |

---

## 二、低覆盖率模块清单（<60%）及原因

| 模块 | 覆盖率 | 低覆盖原因 | 是否可补 |
|------|--------|-----------|---------|
| `knowledge/crawler/prts_crawler.py` | 0% | 真实网络请求，需 PRTS Wiki 在线 | ❌ CPU 侧难测（需 mock HTTP） |
| `knowledge/crawler/audit_corpus.py` | 0% | 需真实爬取数据 | ❌ 需真实数据 |
| `knowledge/graph/build_graph.py` | 19% | 需真实 PRTS JSON 语料 | ⚠️ 可用 mock JSON 测切分/规则推导 |
| `knowledge/graph/visualize_graph.py` | 0% | 可视化出图，需 matplotlib + 真实图谱 | ❌ 视觉产物难自动化断言 |
| `knowledge/rag/build_rag.py` | 49% | 需真实 embedding + ChromaDB | ⚠️ 切分逻辑可单独测（_pack_paragraphs 等） |
| `knowledge/rag/embedding.py` | 69% | 真实模型加载路径未覆盖 | ⚠️ mock embedder 已覆盖主路径 |
| `knowledge/rag/retrieval_test.py` | 0% | 脚本而非模块，手动运行 | ❌ 非测试目标 |
| `knowledge/mcp_tools/server.py` | 0% | MCP 服务端，需 MCP 客户端连接 | ⚠️ 可用 mcp 库的测试客户端 |
| `action/adb_controller.py` | 48% | 真实 ADB 命令执行，mock 不覆盖 | ⚠️ 异常路径可测（连接失败/超时） |
| `training/sft_train.py` | ~30% | V100 专属，CPU 只跑 dry-run | ❌ 真实训练需 GPU |

---

## 三、已补测试清单（本批次）

### 3.1 `tests/test_episode_store.py`（24 用例）

**补前覆盖率**：39% → **补后约 95%**

覆盖：
- `safe_episode_id`：正常/空/特殊字符/中文替换
- `check_id`：合法/非法（斜杠/空格/空/超长）
- `save/get/exists`：tmp_path 隔离，CRUD 全流程
- `save` 自动创建目录、非法 ID 抛异常
- `list_ids`：空目录/不存在目录/排序/只返回 .json
- `list_meta`：字段完整性、reward 缺失、损坏 JSON 抛异常
- `DEFAULT_EPISODE_DIR` 常量

### 3.2 `tests/test_graph_query.py`（23 用例）

**补前覆盖率**：23% → **补后约 90%**

用 6 节点 8 边 mock 小图（2干员/2敌人/1关卡/1技能），直接注入 `GraphQuery.graph`，绕过 GraphML 加载：

- `skills_of_operator`：有技能/无技能
- `enemies_in_stage`：敌人列表/字段完整性/空关卡
- `operators_countering`：克制干员/evidence=inferred/无克制
- `enemies_countered_by`：被克制敌人/规则字段/无克制
- `operators_for_stage`：推荐干员/按 score 降序/字段/空关卡
- `counter_heavy_armor`：高防敌人/按 score 排序/heavy_enemies 字段/高阈值无匹配/缓存
- `_resolve_enemy`：精确匹配/不存在回退
- `stats`：节点/边按类型统计

### 3.3 `tests/test_bm25_retriever.py`（22 用例）

**任务A产物**，覆盖：
- `rrf_fuse`：单路/双路叠加/空路/重复/来源追踪
- `_tokenize`：中文/英文数字/空/标点过滤
- `_inject_entity_dictionary`：实体名注入/关卡编号前缀
- `BM25Index`（手动构造小索引）：检索排序/doc_type 过滤/空 query/无匹配/count
- `Retriever`（mock 注入）：Top-K/显式指名重排/关卡编号边界/非法 doc_type/BM25 禁用降级/RRF_K 常量

---

## 四、用户指定优先模块覆盖率

用户要求优先补的模块，当前覆盖率均已 >88%，无需额外补测试：

| 模块 | 覆盖率 | 说明 |
|------|--------|------|
| `agent/decision_loop.py` | 96% | 边界已覆盖（main 入口/mock loop/异常） |
| `env/arknights_env.py` | 94% | 异常路径已覆盖（执行失败/状态异常） |
| `knowledge/mcp_tools/service.py` | 91% | 工具边界已覆盖（空查询/不存在实体） |
| `action/action_executor.py` | 94% | 失败路径已覆盖（动作失败不中断序列） |

---

## 五、后续优化建议

1. **`build_graph.py` 规则推导**：可用 mock JSON 测 `derive_counter_rules` 的 R1/R2/R3 触发（参考 `tests/test_chunking_and_rules.py` 模式）
2. **`build_rag.py` 切分逻辑**：`_pack_paragraphs`/`chunk_operator` 等纯函数可用 fixture 输入测
3. **`adb_controller.py` 异常路径**：mock subprocess 测连接失败/超时/设备离线
4. **`mcp_tools/server.py`**：用 mcp 库的测试客户端测工具注册和调用
5. **全量覆盖率**：沙箱内存升级后可一次性跑 `pytest --cov=. --cov-report=html` 生成完整报告

---

## 六、运行方式

```bash
# 单模块覆盖率
pytest tests/test_episode_store.py --cov=env.episode_store --cov-report=term-missing

# 分批跑（沙箱 4GB 限制）
pytest tests/test_agent.py tests/test_env.py tests/test_e2e_mock.py --cov=agent --cov=env
pytest tests/test_bm25_retriever.py tests/test_knowledge_port.py tests/test_mcp_tools.py --cov=knowledge

# 全量（需 8GB+ 内存）
pytest --cov=. --cov-report=term-missing --cov-report=html
```
