# knowledge —— 知识库

- `crawler/`：PRTS Wiki 爬虫（干员 / 敌人 / 关卡 / 攻略），输出到 `data/prts_raw/`（不提交）
- `rag/`：Embedding + ChromaDB 向量库 + 检索器
- `graph/`：NetworkX 知识图谱（干员-技能-敌人-关卡 关系）
- `mcp_tools/`：MCP 工具集（参考 PRTS MCP Server 的工具集），供 LLM Agent 调用

第二批实现。爬取数据与构建索引分离，便于知识库增量更新。
