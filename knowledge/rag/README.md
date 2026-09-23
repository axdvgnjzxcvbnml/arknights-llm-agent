# rag —— 检索增强（RAG）

- `embedding.py`：中文 Embedding（BAAI/bge-small-zh-v1.5）
- `vector_store.py`：ChromaDB 向量库（持久化到 `data/vector_store/`）
- `retriever.py`：给定 query 返回 Top-K 相关文档

构建入口：`scripts/build_rag.sh`（把爬取的 JSON 切分、向量化、入库）。
第二批实现。
