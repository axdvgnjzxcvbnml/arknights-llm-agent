"""ChromaDB 向量存储封装：持久化、collection 管理、upsert 与过滤检索。

- 持久化目录与 collection 名来自 configs/knowledge.yaml；
- 写入使用 upsert（相同 id 覆盖），重复构建不产生重复文档；
- 检索支持 Chroma where 子句按 metadata 过滤（如 {"type": "operator"}）。
"""

import os

__all__ = ["KnowledgeStore"]


class KnowledgeStore(object):
    def __init__(self, persist_dir, collection, distance="cosine"):
        # type: (str, str, str) -> None
        import chromadb

        self.persist_dir = persist_dir
        self.collection_name = collection
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        metadata = {"hnsw:space": distance} if distance else None
        self.collection = self._client.get_or_create_collection(
            name=collection, metadata=metadata
        )

    def count(self):
        # type: () -> int
        return self.collection.count()

    def upsert(self, ids, embeddings, documents, metadatas):
        # type: (list, list, list, list) -> None
        """批量写入/覆盖文档。id 相同则覆盖，避免重复爬取重建时产生重复。"""
        if not ids:
            return
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(self, embedding, k=5, where=None):
        # type: (list, int, dict) -> list
        """向量检索，返回 list[dict]：document/metadata/distance（按相关度降序）。"""
        kwargs = {
            "query_embeddings": [embedding],
            "n_results": k,
        }
        if where:
            kwargs["where"] = where
        res = self.collection.query(**kwargs)
        if not res or not res.get("ids") or not res["ids"][0]:
            return []
        out = []
        for i in range(len(res["ids"][0])):
            out.append({
                "id": res["ids"][0][i],
                "document": res["documents"][0][i],
                "metadata": res["metadatas"][0][i] or {},
                "distance": float(res["distances"][0][i]),
            })
        return out

    def reset_collection(self):
        # type: () -> None
        """删除并重建 collection（--rebuild 时使用，清掉旧切分/旧元数据）。"""
        self._client.delete_collection(self.collection_name)
        self.collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata=self.collection.metadata,
        )
