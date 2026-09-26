"""RAG 检索器：向量检索 + BM25 关键词检索，RRF 融合。

两路检索互补：
- 向量检索（bge-small-zh）：语义相似，擅长"意思相近但用词不同"
- BM25 关键词检索：精确术语匹配，擅长"专有名词/技能名/敌人名"
- RRF（Reciprocal Rank Fusion）融合：score = sum(1/(k + rank))，k=60

返回结构（便于 LLM 引用来源、可解释性）：
    [
      {"content": str, "score": float,
       "metadata": {"source": str, "type": str, "section": str, "url": str}},
      ...
    ]
score 为 RRF 融合分数（越大越相关），evidence 仍为 retrieved。

排序：RRF 融合后，叠加一个保守的"显式指名"重排——当 query 原文明确出现某候选
实体名时，优先于"名字只是其超串但未被指名"的候选（典型：问"能天使"时，异格"新约能天使"
不应排在本体前面）。不改动向量、不改动 evidence（仍为 retrieved）。
"""

import re

from .bm25_index import BM25Index
from .config import DEFAULT_CONFIG_PATH, load_knowledge_config
from .embedding import load_embedder
from .vector_store import KnowledgeStore

__all__ = ["Retriever", "rrf_fuse"]

# 允许的类型白名单（与 build_rag 元数据一致）
VALID_TYPES = ("operator", "enemy", "stage", "guide")

# RRF 常数（论文推荐 k=60）
RRF_K = 60


def rrf_fuse(rank_lists, k=RRF_K):
    # type: (List[List[dict]], int) -> List[dict]
    """Reciprocal Rank Fusion：合并多路排名结果。

    :param rank_lists: 每路是 [{"content","metadata","rank"}, ...]，按相关度降序
    :param k: RRF 常数，默认 60
    :return: 融合后的 [{"content","score","metadata","rrf_sources"}, ...]，按分数降序
    """
    fused = {}  # content -> {score, metadata, rrf_sources}
    for path_idx, rlist in enumerate(rank_lists):
        for item in rlist:
            content = item["content"]
            rank = item.get("rank", 0)
            score = 1.0 / (k + rank + 1)  # rank 从 0 开始
            if content not in fused:
                fused[content] = {
                    "content": content,
                    "score": 0.0,
                    "metadata": item.get("metadata", {}),
                    "rrf_sources": [],
                }
            fused[content]["score"] += score
            fused[content]["rrf_sources"].append(path_idx)
    results = sorted(fused.values(), key=lambda x: -x["score"])
    for r in results:
        r["score"] = round(r["score"], 6)
    return results


def _explicitly_named(meta, query):
    # type: (dict, str) -> bool
    """query 是否明确点名了该 chunk 的实体（source；关卡再取编号前缀）。

    ASCII 名（如关卡编号 3-8、12F）要求两侧不是字母数字，避免 "1-1" 误命中 "11-1"；
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
    """混合检索器：向量 + BM25，RRF 融合。

    用法：
        ret = Retriever()
        hits = ret.search("能天使的技能是什么", k=5)
        hits = ret.search("碎骨", k=5, doc_type="enemy")
    """

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH,
                 bm25_index=None, use_bm25=True):
        # type: (dict, str, Optional[BM25Index], bool) -> None
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
        self.use_bm25 = use_bm25
        self._bm25 = bm25_index  # 允许注入（测试用）；None 时懒加载

    @property
    def bm25(self):
        """懒加载 BM25 索引（首次访问时构建/加载缓存）。"""
        if self._bm25 is None and self.use_bm25:
            self._bm25 = BM25Index(config=self.config)
        return self._bm25

    def _vector_search(self, query, k, doc_type=None):
        """纯向量检索（保留原有显式指名重排逻辑）。"""
        query_vec = self.embedder.encode_query(query)
        where = {"type": doc_type} if doc_type else None
        # 超取候选池再做"显式指名"重排
        pool_k = max(k, min(k * 4, 20))
        rows = self.store.query(query_vec, k=pool_k, where=where)
        pool = []
        for idx, row in enumerate(rows):
            pool.append({
                "_idx": idx,
                "content": row["document"],
                "score": round(1.0 - row["distance"], 4),
                "metadata": row["metadata"],
            })
        pool.sort(key=lambda r: (0 if _explicitly_named(r["metadata"], query) else 1,
                                 -float(r["score"]), r["_idx"]))
        results = []
        for rank, r in enumerate(pool[:k]):
            results.append({"content": r["content"], "score": r["score"],
                            "metadata": r["metadata"], "rank": rank})
        return results

    def _bm25_search(self, query, k, doc_type=None):
        """BM25 关键词检索。"""
        if not self.use_bm25 or self.bm25 is None:
            return []
        return self.bm25.search(query, k=k, doc_type=doc_type)

    def search(self, query, k=None, doc_type=None):
        # type: (str, int, str) -> list
        """混合检索 Top-K：向量 + BM25，RRF 融合。

        doc_type 可限 operator/enemy/stage/guide。
        返回 [{"content", "score", "metadata"}, ...]，score 为 RRF 融合分数。
        """
        if doc_type is not None and doc_type not in VALID_TYPES:
            raise ValueError("doc_type 必须是 %s 之一" % (VALID_TYPES,))
        k = k or self.top_k

        # 两路各超取，融合后取 Top-K
        pool_k = max(k * 2, 10)

        vec_results = self._vector_search(query, k=pool_k, doc_type=doc_type)
        bm25_results = self._bm25_search(query, k=pool_k, doc_type=doc_type)

        if not bm25_results:
            # BM25 不可用时降级为纯向量
            return [{"content": r["content"], "score": r["score"],
                     "metadata": r["metadata"]} for r in vec_results[:k]]

        # RRF 融合
        fused = rrf_fuse([vec_results, bm25_results], k=RRF_K)

        # 显式指名重排（在 RRF 分数基础上微调）
        fused.sort(key=lambda r: (0 if _explicitly_named(r["metadata"], query) else 1,
                                   -float(r["score"])))

        results = []
        for r in fused[:k]:
            results.append({"content": r["content"], "score": r["score"],
                            "metadata": r["metadata"]})
        return results
