"""BM25 关键词检索索引：与向量检索互补，提升精确术语匹配。

从 ChromaDB 读取所有 chunk 原文，建 BM25Okapi 索引，缓存到
data/vector_store/bm25_index/（pickle，gitignored）。首次构建后后续直接加载缓存。

中文分词：轻量正则分词（中文字符单独 + 英文/数字连续成词），不依赖 jieba。
对短文本（PRTS chunk 200-500 字）效果足够；如需更准可换 jieba（改 _tokenize 即可）。

与向量检索的关系：
- 向量检索：语义相似，擅长"意思相近但用词不同"
- BM25：关键词精确匹配，擅长"专有名词/技能名/敌人名"
- 两者用 RRF（Reciprocal Rank Fusion）融合，取各自 Top-N 候选后按排名倒数加权
"""

import os
import pickle
import re
import time
from typing import List, Optional

import jieba

from .config import DEFAULT_CONFIG_PATH, load_knowledge_config
from .vector_store import KnowledgeStore

__all__ = ["BM25Index"]

# 英文/数字连续成 token（jieba 已处理，这里兜底）
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """jieba 分词（已注入 PRTS 专有名词词典）+ 英文数字兜底。"""
    tokens = list(jieba.cut(text or ""))
    # 过滤空 token 和纯标点
    return [t for t in tokens if t.strip() and not re.match(r"^[^\w\u4e00-\u9fff]+$", t)]


def _inject_entity_dictionary(metas):
    """从 chunk metadata 提取 PRTS 实体名，注入 jieba 用户词典。

    干员名/敌人名/关卡名通常是 2-6 字专有名词，jieba 默认词典不认识，
    注入后才能正确分词（如"能天使"不再被切成"能/天使"）。
    """
    entity_names = set()
    for meta in metas:
        if not meta:
            continue
        source = str(meta.get("source") or "").strip()
        if source and 2 <= len(source) <= 20:
            entity_names.add(source)
        # 关卡编号前缀（如"3-8"从"3-8 黄昏"提取）
        if meta.get("type") == "stage":
            head = source.split(" ")[0].strip()
            if head and head != source:
                entity_names.add(head)
    for name in entity_names:
        # freq=1000 确保优先按整词切分
        jieba.add_word(name, freq=1000)
    return len(entity_names)


class BM25Index(object):
    """BM25 关键词索引：从 ChromaDB 构建，支持按 doc_type 过滤的 Top-K 检索。

    用法：
        idx = BM25Index()               # 自动构建或加载缓存
        hits = idx.search("能天使 技能", k=10)
        hits = idx.search("碎骨", k=10, doc_type="enemy")
    """

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH,
                 force_rebuild=False):
        self.config = config or load_knowledge_config(config_path)
        rag_cfg = self.config["rag"]
        vs = rag_cfg["vector_store"]
        self.persist_dir = vs["persist_dir"]
        self.collection = vs["collection"]
        self.cache_dir = os.path.join(self.persist_dir, "bm25_index")
        self.cache_path = os.path.join(self.cache_dir, "bm25_okapi.pkl")

        self._bm25 = None
        self._docs = []          # List[str]，与 ids 一一对应
        self._ids = []           # List[str]，ChromaDB chunk id
        self._metas = []         # List[dict]，与 ids 一一对应
        self._type_index = {}    # doc_type -> List[int]，用于过滤

        if force_rebuild or not self._load_cache():
            self._build_from_store()
            self._save_cache()

    # ---------------------------------------------------------------- 构建/缓存
    def _build_from_store(self):
        """从 ChromaDB 读取全部 chunk，构建 BM25 索引。"""
        from rank_bm25 import BM25Okapi

        store = KnowledgeStore(
            persist_dir=self.persist_dir,
            collection=self.collection,
            distance="cosine",
        )
        t0 = time.time()
        # ChromaDB get 全部（offset/limit 翻页）
        all_ids, all_docs, all_metas = [], [], []
        offset = 0
        page_size = 5000
        while True:
            batch = store.collection.get(
                limit=page_size, offset=offset,
                include=["documents", "metadatas"])
            ids = batch.get("ids", [])
            docs = batch.get("documents", [])
            metas = batch.get("metadatas", [])
            if not ids:
                break
            all_ids.extend(ids)
            all_docs.extend(docs)
            all_metas.extend(metas)
            if len(ids) < page_size:
                break
            offset += page_size

        self._ids = all_ids
        self._docs = all_docs
        self._metas = all_metas or [{} for _ in all_ids]

        # 建类型索引
        self._type_index = {}
        for i, meta in enumerate(self._metas):
            t = (meta or {}).get("type", "")
            self._type_index.setdefault(t, []).append(i)

        # 注入 PRTS 专有名词到 jieba（干员/敌人/关卡名）
        n_entities = _inject_entity_dictionary(self._metas)

        # 分词 + 建 BM25
        tokenized = [_tokenize(doc) for doc in self._docs]
        self._bm25 = BM25Okapi(tokenized)
        print("[bm25] 构建完成：%d chunks，%d 实体名词注入，耗时 %.1fs"
              % (len(self._docs), n_entities, time.time() - t0))

    def _save_cache(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self.cache_path, "wb") as f:
            pickle.dump({
                "ids": self._ids,
                "docs": self._docs,
                "metas": self._metas,
                "type_index": self._type_index,
                "bm25": self._bm25,
            }, f)
        print("[bm25] 缓存已写入 %s" % self.cache_path)

    def _load_cache(self) -> bool:
        if not os.path.exists(self.cache_path):
            return False
        try:
            with open(self.cache_path, "rb") as f:
                data = pickle.load(f)
            self._ids = data["ids"]
            self._docs = data["docs"]
            self._metas = data["metas"]
            self._type_index = data["type_index"]
            self._bm25 = data["bm25"]
            print("[bm25] 从缓存加载：%d chunks" % len(self._docs))
            return True
        except Exception as e:
            print("[bm25] 缓存加载失败（%s），将重建" % type(e).__name__)
            return False

    # ---------------------------------------------------------------- 检索
    def search(self, query: str, k: int = 10, doc_type: Optional[str] = None) -> List[dict]:
        """BM25 检索 Top-K。

        :return: [{"content", "score", "metadata", "rank"}, ...]，按 BM25 分数降序
        """
        if self._bm25 is None:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []

        # 全量打分
        scores = self._bm25.get_scores(tokens)

        # 类型过滤
        if doc_type:
            valid_indices = set(self._type_index.get(doc_type, []))
            scored = [(i, s) for i, s in enumerate(scores) if i in valid_indices and s > 0]
        else:
            scored = [(i, s) for i, s in enumerate(scores) if s > 0]

        # 按分数降序
        scored.sort(key=lambda x: -x[1])
        results = []
        for rank, (idx, score) in enumerate(scored[:k]):
            results.append({
                "content": self._docs[idx],
                "score": round(float(score), 4),
                "metadata": self._metas[idx],
                "rank": rank,
            })
        return results

    def count(self) -> int:
        return len(self._docs)
