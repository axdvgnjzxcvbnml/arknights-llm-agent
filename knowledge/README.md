# knowledge —— 知识库

- `crawler/`：PRTS Wiki 爬虫（干员 / 敌人 / 主线关卡 / 活动关卡 / 攻略），输出到 `data/prts_raw/`（不提交）
- `rag/`：Embedding + ChromaDB 向量库 + 检索器
- `graph/`：NetworkX 知识图谱（干员-技能-敌人-关卡 关系）
- `mcp_tools/`：MCP 工具集（6 个工具：query_operator / query_skill / query_enemy / query_stage / search_guide / recommend_operators），供 LLM Agent 调用

第二批实现。爬取数据与构建索引分离，便于知识库增量更新。

---

## 爬取类型

| 类型 | PRTS 分类 | 输出子目录 | 说明 |
|------|----------|-----------|------|
| `operator` | Category:干员 | `operators/` | 460 页，含异格形态 |
| `enemy` | Category:敌人 | `enemies/` | 500+ 页，需翻页 |
| `stage` | Category:主线关卡 | `stages/` | 487 页，标题格式"3-8 黄昏" |
| `event_stage` | Category:活动关卡 | `stages_event/` | SideStory/故事集/联锁竞赛等 **[分类名待验证]** |
| `annihilation` | Category:剿灭作战 | `stages_event/` | 长期剿灭关卡 **[分类名待验证]** |
| `contingency` | Category:保全派驻 | `stages_event/` | 保全派驻模式 **[分类名待验证]** |

> **活动关卡分类名标注**：PRTS 503 期间无法实测分类名，恢复后需确认 `Category:活动关卡` / `Category:剿灭作战` / `Category:保全派驻` 是否正确。若分类名不同，修改 `knowledge/crawler/batch_crawl.py` 的 `CATEGORY_MAP` 即可。

### 活动关卡说明

- 活动关 HTML 结构与主线类似，但可能没有"突袭"章节，`parse_stages.py` 对缺失章节安全返回空；
- 活动关输出到 `stages_event/` 子目录，与主线 `stages/` 区分，避免 RAG 建库时混淆；
- `build_rag.py` 和 `build_graph.py` 会自动合并 `stages/` + `stages_event/`，无需额外配置；
- 活动关标题格式多样（OF-1 / CB-EX1 / IC-9 等），`_safe_name` 已处理 `/` 和 `:`。

---

## 使用方法

### 1. 批量爬取

```bash
# 主线关卡（已爬全量 487 页）
python -m knowledge.crawler.batch_crawl --type stage --limit 500

# 活动关卡（小规模验证）
python -m knowledge.crawler.batch_crawl --type event_stage --limit 20

# 剿灭作战
python -m knowledge.crawler.batch_crawl --type annihilation --limit 10

# 断点续爬（已存在的 JSON 自动跳过）
python -m knowledge.crawler.batch_crawl --type event_stage --limit 100

# 强制重爬
python -m knowledge.crawler.batch_crawl --type event_stage --limit 20 --force
```

### 2. 构建向量库

```bash
python -m knowledge.rag.build_rag
# 自动合并 stages/ + stages_event/
```

### 3. 构建知识图谱

```bash
python -m knowledge.graph.build_graph
# 自动合并 stages/ + stages_event/
```

### 4. MCP 工具

Agent 通过 `agent/knowledge_port.py` 的 `MCPKnowledge` 类调用全部 6 个 MCP 工具：
- `query_operator(name)` — 干员完整信息（fact）
- `query_skill(operator, skill_name)` — 技能详情（fact）
- `query_enemy(name, level=None)` — 敌人属性（fact）
- `query_stage(stage_id)` — 关卡信息和敌情（fact）
- `search_guide(query, k, doc_type)` — RAG 检索攻略（retrieved）
- `recommend_operators(stage_id, constraints)` — 图谱推荐干员（inferred）

evidence 分级严格：`fact`（PRTS 结构化事实）/ `retrieved`（RAG 参考资料）/ `inferred`（图谱规则推断）。
