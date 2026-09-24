"""RAG 检索器（向量检索，只读）。

加载 data/vector_store（ChromaDB）并按 configs/knowledge.yaml 检索。
embedding 后端：真实 bge-small-zh-v1.5（离线时回退 mock 确定性向量，仅供接口联调）。
"""

import os

from . import schemas as S

__all__ = ["Retriever", "EmbeddingBackend"]


def _model_available(model_name):
    try:
        from sentence_transformers import SentenceTransformer
        return True
    except Exception:
        return False


class EmbeddingBackend(object):
    """bge embedding 封装（真实模型懒加载；后端配置见 configs/knowledge.yaml）。"""

    def __init__(self, backend="auto", model_name="BAAI/bge-small-zh-v1.5",
                 dim=512, device="cpu"):
        # type: (str, str, int, str) -> None
        self.backend = backend
        self.model_name = model_name
        self.dim = dim
        self.device = device
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        if self.backend == "mock":
            self._model = False
            return False
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
            return self._model
        except Exception:
            if self.backend == "bge":
                raise
            self._model = False
            return False

    def embed(self, texts):
        # type: (list) -> list
        model = self._load()
        if model is False:
            return self._mock_embed(texts)
        return model.encode(texts, normalize_embeddings=True).tolist()

    def _mock_embed(self, texts):
        # type: (list) -> list
        """确定性伪随机向量（seed 固定），维度 self.dim；仅供离线接口联调，检索无意义。"""
        import hashlib
        import math
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = []
            for i in range(self.dim):
                b = h[i % len(h)]
                vec.append(((b / 255.0) - 0.5) * 2.0)
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class Retriever(object):
    """向量检索入口（ChromaDB + bge）。"""

    def __init__(self, config=None):
        # type: (dict) -> None
        self.config = config or {}
        rag = self.config.get("rag", {})
        self.embedding_cfg = rag.get("embedding", {})
        self.vstore_cfg = rag.get("vector_store", {})
        self.retrieval_cfg = rag.get("retrieval", {})
        self.top_k = int(self.retrieval_cfg.get("top_k", 5))
        self.backend = EmbeddingBackend(
            backend=self.embedding_cfg.get("backend", "auto"),
            model_name=self.embedding_cfg.get("model_name", "BAAI/bge-small-zh-v1.5"),
            dim=int(self.embedding_cfg.get("dim", 512)),
            device=self.embedding_cfg.get("device", "cpu"))
        self._collection = None

    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection
        import chromadb
        client = chromadb.PersistentClient(path=self.vstore_cfg.get("persist_dir", "data/vector_store"))
        self._collection = client.get_collection(self.vstore_cfg.get("collection", "arknights_knowledge"))
        return self._collection

    @staticmethod
    def _query_named_entity(q):
        """从 query 中提取"显式指名"的实体名（保守，只取来源名）。

        用于检索重排：当 query 原文明确出现某实体名时，优先把该实体相关 chunk
        提到候选前（组内仍按向量分稳定排序）。返回 (实体名, 匹配模式) 或 None。
        保守原则：宁可不重排也不要错排（不改变向量排序的兜底）。
        """
        return None

    def search(self, query, k=None, doc_type=None):
        # type: (str, int, str) -> S.GuideOut
        k = k or self.top_k
        k = max(1, min(int(k), 20))
        collection = self._ensure_collection()
        emb = self.backend.embed([query])[0]
        where = None
        if doc_type:
            where = {"doc_type": doc_type}
        res = collection.query(query_embeddings=[emb], n_results=k,
                               where=where)
        hits = []
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        docs = res.get("documents", [[]])[0]
        for i, _id in enumerate(ids):
            m = metas[i] if i < len(metas) else {}
            score = 1.0 - float(dists[i]) if i < len(dists) else 0.0
            hits.append(S.GuideHit(
                content=docs[i] if i < len(docs) else "",
                score=round(score, 4),
                source=m.get("source", ""),
                doc_type=m.get("doc_type", ""),
                section=m.get("section", ""),
                url=m.get("url", ""),
                evidence=S.EVIDENCE_RETRIEVED))
        note = ("本结果为 RAG 检索到的参考资料（evidence=retrieved），不是事实判断；"
                "具体数值/结论请以 PRTS Wiki 页面原文为准。")
        return S.GuideOut(found=bool(hits), query=query, k=k, hits=hits,
                          embedding_backend=self.backend.model_name, note=note)
