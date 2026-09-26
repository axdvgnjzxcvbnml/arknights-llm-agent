"""knowledge/rag/build_rag.py 分批向量化回归测试（审计 H3）。

旧缺陷：range 步长读了配置 batch_size，但切片硬编码 +32，二者不一致时
- 单次 encode 可能超过配置批次（显存风险）；
- 向量总数与 chunk 数失配。
这里不依赖真实 bge/chroma：用 fake embedder 记录每批大小、fake store 记录 upsert，
并把 JSON 加载与切分函数 monkeypatch 成可控桩，专门验证"步长==切片"统一用 bs。
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from knowledge.rag import build_rag  # noqa: E402


class _RecordingEmbedder(object):
    backend = "mock"
    dim = 8

    def __init__(self, batch_size):
        self.batch_size = batch_size
        self.batch_lengths = []

    def encode(self, texts):
        n = len(texts)
        self.batch_lengths.append(n)
        if n > self.batch_size:
            raise AssertionError(
                "单次 encode 收到 %d 条，超过配置 batch_size=%d（步长/切片未统一）"
                % (n, self.batch_size))
        return [[float(i)] * self.dim for i in range(n)]


class _RecordingStore(object):
    def __init__(self, *args, **kwargs):
        self.upserted = 0
        self.reset = False

    def reset_collection(self):
        self.reset = True

    def count(self):
        return self.upserted

    def upsert(self, ids, vectors, texts, metadatas):
        assert len(ids) == len(vectors) == len(texts) == len(metadatas)
        self.upserted += len(ids)


def _patch_pipeline(monkeypatch, batch_size):
    """返回 (fake_embedder, fake_store_factory)，并替换 IO/切分依赖。"""
    embedder = _RecordingEmbedder(batch_size)
    monkeypatch.setattr(build_rag, "load_embedder", lambda cfg: embedder)

    store_holder = {}

    def _factory(*args, **kwargs):
        if "store" not in store_holder:
            store_holder["store"] = _RecordingStore()
        return store_holder["store"]

    monkeypatch.setattr(build_rag, "KnowledgeStore", _factory)

    # 三类各 3 个实体，每实体固定产出若干 chunk：operator 3 / enemy 2 / stage 5 => 合计 30
    def _load(subdir, raw_dir):
        n = {"operators": 3, "enemies": 3, "stages": 3}[subdir]
        return [("%s_%d" % (subdir.rstrip("s"), i), {"name": "x%d" % i}) for i in range(n)]

    monkeypatch.setattr(build_rag, "_load_json_dir", _load)

    def _chunks(n, doc_type):
        def _fn(data, max_chars=500, source=None):
            # 每条 490 字（<500 且加上下一条会超 500），保证一段一块、恰好 n 块
            paras = ["a" * 490 for _ in range(n)]
            return build_rag._make_chunks(
                doc_type, source or "s", "sec", "http://x/%s" % source,
                paras, max_chars)
        return _fn

    monkeypatch.setattr(build_rag, "chunk_operator", _chunks(3, "operator"))
    monkeypatch.setattr(build_rag, "chunk_enemy", _chunks(2, "enemy"))
    monkeypatch.setattr(build_rag, "chunk_stage", _chunks(5, "stage"))
    return embedder, (lambda: store_holder["store"])


def _config(tmp_path, batch_size):
    return {
        "rag": {
            "build": {
                "raw_dir": str(tmp_path / "raw"),
                "chunk_max_chars": 500,
                "include_guides": False,  # 只测向量化分批，不生成攻略 chunk
            },
            "embedding": {"backend": "mock", "batch_size": batch_size},
            "vector_store": {
                "persist_dir": str(tmp_path / "vec"),
                "collection": "ark",
                "distance": "cosine",
            },
        }
    }


@pytest.mark.parametrize("batch_size,total", [(7, 30), (32, 30), (1, 30), (13, 30)])
def test_encode_batch_respects_configured_batch_size(monkeypatch, tmp_path, batch_size, total):
    embedder, store_getter = _patch_pipeline(monkeypatch, batch_size)
    stats = build_rag.build_all(_config(tmp_path, batch_size), rebuild=True)

    # 每批都不超过 bs
    assert embedder.batch_lengths, "至少应调用一次 encode"
    assert all(0 < n <= batch_size for n in embedder.batch_lengths)
    # 向量总数 == chunk 总数（旧 +32 切片在 bs!=32 时会失配）
    assert sum(embedder.batch_lengths) == total
    assert stats["chunks_total"] == total
    # 全部入库
    assert store_getter().upserted == total
    assert store_getter().reset is True
