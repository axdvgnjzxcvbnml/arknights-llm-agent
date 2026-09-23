"""文本向量化：封装 BAAI/bge-small-zh-v1.5（512 维，中文检索）。

- backend="bge"：加载真实 bge 模型（CPU 可跑，V100 上 device=cuda 更快）；
- backend="mock"：确定性伪随机向量，仅供离线环境做接口/链路联调，检索无意义；
- backend="auto"：优先真实模型，加载失败自动回退 mock 并打印告警。

# TODO-V100: V100 环境在 configs/knowledge.yaml 中将 device 改为 cuda；
#            离线/无法下载模型的环境才使用 mock，正式检索必须用真实 bge。
"""

import hashlib
import logging

import numpy as np

__all__ = ["Embedder", "load_embedder"]

LOGGER = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DEFAULT_DIM = 512
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class _BaseEmbedder(object):
    def __init__(self, dim):
        # type: (int) -> None
        self.dim = dim
        self.backend = "base"

    def encode(self, texts):
        # type: (list) -> list
        raise NotImplementedError

    def encode_query(self, text):
        # type: (str) -> list
        """检索 query 向量化（bge 中文模型建议加检索指令前缀）。"""
        return self.encode([text])[0]


class BgeEmbedder(_BaseEmbedder):
    """真实 bge-small-zh-v1.5 向量器（sentence-transformers 加载）。"""

    def __init__(self, model_name=DEFAULT_MODEL_NAME, dim=DEFAULT_DIM,
                 device="cpu", batch_size=32):
        # type: (str, int, str, int) -> None
        super(BgeEmbedder, self).__init__(dim)
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=device)
        # 兼容新旧版本：6.x 重命名为 get_embedding_dimension，2.x 为旧方法名
        get_dim = getattr(self.model, "get_embedding_dimension", None) \
            or getattr(self.model, "get_sentence_embedding_dimension")
        got_dim = int(get_dim())
        if got_dim != dim:
            LOGGER.warning("配置维度 %d 与模型实际输出维度 %d 不一致，以模型为准", dim, got_dim)
            self.dim = got_dim
        self.backend = "bge"

    def encode(self, texts):
        # type: (list) -> list
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32).tolist()

    def encode_query(self, text):
        # type: (str) -> list
        # bge 中文模型官方建议：检索侧 query 添加指令前缀
        return self.encode([BGE_QUERY_INSTRUCTION + text])[0]


class MockEmbedder(_BaseEmbedder):
    """# TODO-V100: 离线联调用确定性伪随机向量，无语义检索能力，V100/联网环境必须替换为 bge。"""

    def __init__(self, dim=DEFAULT_DIM):
        # type: (int) -> None
        super(MockEmbedder, self).__init__(dim)
        self.backend = "mock"

    def _vector_for(self, text):
        # type: (str) -> list
        seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        vec = rng.randn(self.dim).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec.tolist()

    def encode(self, texts):
        # type: (list) -> list
        return [self._vector_for(t) for t in texts]

    def encode_query(self, text):
        # type: (str) -> list
        return self._vector_for(text)


def _make_bge(cfg):
    # type: (dict) -> BgeEmbedder
    return BgeEmbedder(
        model_name=cfg.get("model_name", DEFAULT_MODEL_NAME),
        dim=int(cfg.get("dim", DEFAULT_DIM)),
        device=cfg.get("device", "cpu"),
        batch_size=int(cfg.get("batch_size", 32)),
    )


def load_embedder(config):
    # type: (dict) -> _BaseEmbedder
    """按配置加载向量器。config 为 knowledge.yaml 中 rag.embedding 段。"""
    cfg = config or {}
    backend = cfg.get("backend", "auto")
    if backend == "mock":
        LOGGER.warning("使用 MockEmbedder（伪随机向量，仅用于接口联调，检索结果无意义）")
        return MockEmbedder(dim=int(cfg.get("dim", DEFAULT_DIM)))
    if backend == "bge":
        return _make_bge(cfg)
    # auto
    try:
        return _make_bge(cfg)
    except Exception as exc:  # 模型下载/加载失败：回退 mock，不阻断骨架联调
        LOGGER.warning("bge 模型加载失败（%s），回退 MockEmbedder；"
                       "正式检索请在可联网/V100 环境重建向量库", exc)
        return MockEmbedder(dim=int(cfg.get("dim", DEFAULT_DIM)))
