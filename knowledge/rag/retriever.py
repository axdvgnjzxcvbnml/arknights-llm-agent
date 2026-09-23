"""RAG 检索器：query -> Top-K 相关 chunk，支持按 type 过滤。

返回结构（便于 LLM 引用来源、可解释性）：
    [
      {"content": str, "score": float,
       "metadata": {"source": str, "type": str, "section": str, "url": str}},
      ...
    ]
score 统一归一化为相似度（越大越相关）：cosine 距离 -> 1 - distance。
"""

from .config import DEFAULT_CONFIG_PATH, load_knowledge_config
from .embedding import load_embedder
from .vector_store import KnowledgeStore

__all__ = ["Retriever"]

# 允许的类型白名单（与 build_rag 元数据一致）
VALID_TYPES = ("operator", "enemy", "stage", "guide")


class Retriever(object):
    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        # type: (dict, str) -> None
        self.config = config or load_knowledge_config(config_path)
        rag_cfg = self.config["rag"]
        self.top_k = int(rag_cfg.get("retrieval", {}).get("top_k", 5))
        self.embedder = load_embedder(rag_cfg.get("embedding", {}))
        vs = rag_cfg["vector_store"]
        self.store = KnowledgeStore(
            persist_dir=vs["persist_dir"],
            collection=vs["collection"],
            distance=vs.get("distance", "cosine"),
        )

    def search(self, query, k=None, doc_type=None):
        # type: (str, int, str) -> list
        """检索 Top-K。doc_type 可限 operator/enemy/stage/guide。"""
        if doc_type is not None and doc_type not in VALID_TYPES:
            raise ValueError("doc_type 必须是 %s 之一" % (VALID_TYPES,))
        k = k or self.top_k
        query_vec = self.embedder.encode_query(query)
        where = {"type": doc_type} if doc_type else None
        rows = self.store.query(query_vec, k=k, where=where)
        results = []
        for row in rows:
            results.append({
                "content": row["document"],
                "score": round(1.0 - row["distance"], 4),  # cosine 距离 -> 相似度
                "metadata": row["metadata"],
            })
        return results
