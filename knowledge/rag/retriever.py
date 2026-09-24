"""RAG 检索器：query -> Top-K 相关 chunk，支持按 type 过滤。

返回结构（便于 LLM 引用来源、可解释性）：
    [
      {"content": str, "score": float,
       "metadata": {"source": str, "type": str, "section": str, "url": str}},
      ...
    ]
score 统一归一化为相似度（越大越相关）：cosine 距离 -> 1 - distance。

排序：以向量相似度为主，叠加一个保守的“显式指名”重排——当 query 原文明确出现某候选
实体名时，优先于“名字只是其超串但未被指名”的候选（典型：问“能天使”时，异格“新约能天使”
不应排在本体前面）。不改动向量、不改动 evidence（仍为 retrieved）。
"""

import re

from .config import DEFAULT_CONFIG_PATH, load_knowledge_config
from .embedding import load_embedder
from .vector_store import KnowledgeStore

__all__ = ["Retriever"]

# 允许的类型白名单（与 build_rag 元数据一致）
VALID_TYPES = ("operator", "enemy", "stage", "guide")


def _explicitly_named(meta, query):
    # type: (dict, str) -> bool
    """query 是否明确点名了该 chunk 的实体（source；关卡再取编号前缀）。

    ASCII 名（如关卡编号 3-8、12F）要求两侧不是字母数字，避免 “1-1” 误命中 “11-1”；
    中文名直接做子串匹配（中文相邻字不构成标识符延伸问题）。
    """
    candidates = [str(meta.get("source") or "")]
    if meta.get("type") == "stage":
        head = candidates[0].split(" ")[0].strip()
        if head:
            candidates.append(head)
    for name in candidates:
        name = name.strip()
        if len(name) < 2:
            continue
        if name.isascii():
            if re.search(r"(?<![0-9A-Za-z])" + re.escape(name) + r"(?![0-9A-Za-z])", query):
                return True
        elif name in query:
            return True
    return False


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
        # 超取候选池再做“显式指名”重排，保证被指名实体即使向量分略低也不会跌出 Top-K
        pool_k = max(k, min(k * 4, 20))
        rows = self.store.query(query_vec, k=pool_k, where=where)
        pool = []
        for idx, row in enumerate(rows):
            pool.append({
                "_idx": idx,
                "content": row["document"],
                "score": round(1.0 - row["distance"], 4),  # cosine 距离 -> 相似度
                "metadata": row["metadata"],
            })
        # 主键：是否被 query 显式指名；次键：向量相似度；同序保持原顺序（稳定）
        pool.sort(key=lambda r: (0 if _explicitly_named(r["metadata"], query) else 1,
                                 -float(r["score"]), r["_idx"]))
        results = []
        for r in pool[:k]:
            results.append({"content": r["content"], "score": r["score"],
                            "metadata": r["metadata"]})
        return results
