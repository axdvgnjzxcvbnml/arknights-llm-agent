"""BM25 + 向量混合检索单元测试。

覆盖：
- rrf_fuse 融合逻辑（单路/双路/空路/重复文档）
- _tokenize 分词（jieba + 实体名词注入）
- BM25Index 检索（手动构造小索引，不依赖 ChromaDB）
- Retriever 混合检索（注入 mock embedder/store/bm25）
- 显式指名重排（能天使 vs 新约能天使）
- BM25 不可用时降级纯向量
- doc_type 过滤
"""

import pytest

from knowledge.rag.bm25_index import BM25Index, _tokenize, _inject_entity_dictionary
from knowledge.rag.retriever import Retriever, rrf_fuse, RRF_K, _explicitly_named


# ---------------------------------------------------------------- rrf_fuse
class TestRRFFuse:
    def test_single_path(self):
        """单路结果直接返回，分数为 1/(k+rank+1)。"""
        rlist = [{"content": "a", "metadata": {}, "rank": 0},
                 {"content": "b", "metadata": {}, "rank": 1}]
        out = rrf_fuse([rlist])
        assert len(out) == 2
        assert out[0]["content"] == "a"
        assert out[0]["score"] == round(1.0 / (RRF_K + 1), 6)

    def test_dual_path_boost(self):
        """两路都命中的文档分数叠加，排在只命中一路的前面。"""
        vec = [{"content": "a", "metadata": {}, "rank": 0},
               {"content": "b", "metadata": {}, "rank": 1}]
        bm25 = [{"content": "a", "metadata": {}, "rank": 0},
                {"content": "c", "metadata": {}, "rank": 1}]
        out = rrf_fuse([vec, bm25])
        assert out[0]["content"] == "a"  # 两路都命中，分数最高
        assert len(out) == 3

    def test_empty_paths(self):
        """空路返回空列表。"""
        assert rrf_fuse([]) == []
        assert rrf_fuse([[], []]) == []

    def test_duplicate_in_same_path(self):
        """同一路内重复 content 只算一次（后出现的 rank 不叠加）。"""
        rlist = [{"content": "a", "metadata": {}, "rank": 0},
                 {"content": "a", "metadata": {}, "rank": 1}]
        out = rrf_fuse([rlist])
        assert len(out) == 1
        assert out[0]["content"] == "a"

    def test_rrf_sources_tracking(self):
        """rrf_sources 记录命中了哪几路。"""
        vec = [{"content": "a", "metadata": {}, "rank": 0}]
        bm25 = [{"content": "a", "metadata": {}, "rank": 0}]
        out = rrf_fuse([vec, bm25])
        assert out[0]["rrf_sources"] == [0, 1]


# ---------------------------------------------------------------- _tokenize
class TestTokenize:
    def test_chinese_words(self):
        """中文分词（jieba 默认词典）。"""
        tokens = _tokenize("能天使的技能")
        assert "技能" in tokens
        assert "的" in tokens

    def test_english_number(self):
        """英文/数字连续成 token。"""
        tokens = _tokenize("Qwen3-8B model 123")
        assert "Qwen3" in tokens
        assert "8B" in tokens
        assert "123" in tokens

    def test_empty(self):
        """空文本返回空列表。"""
        assert _tokenize("") == []
        assert _tokenize(None) == []

    def test_punctuation_filtered(self):
        """纯标点被过滤。"""
        tokens = _tokenize("，。！？")
        assert tokens == []


# ---------------------------------------------------------------- 实体词典注入
class TestEntityDictionary:
    def test_inject_from_metas(self):
        """从 metadata 提取实体名注入 jieba。"""
        metas = [
            {"source": "能天使", "type": "operator"},
            {"source": "碎骨", "type": "enemy"},
            {"source": "3-8 黄昏", "type": "stage"},
        ]
        n = _inject_entity_dictionary(metas)
        assert n >= 3  # 能天使、碎骨、3-8（关卡编号前缀）
        # 注入后能天使应被正确分词
        tokens = _tokenize("能天使的技能")
        assert "能天使" in tokens

    def test_stage_code_prefix_extracted(self):
        """关卡编号前缀（如 3-8）从 source 提取。"""
        metas = [{"source": "3-8 黄昏", "type": "stage"}]
        _inject_entity_dictionary(metas)
        tokens = _tokenize("3-8有哪些敌人")
        assert "3-8" in tokens


# ---------------------------------------------------------------- BM25Index（手动构造）
class TestBM25Index:
    def _make_small_index(self):
        """手动构造一个 3 文档的小 BM25Index（不依赖 ChromaDB）。"""
        from rank_bm25 import BM25Okapi
        idx = BM25Index.__new__(BM25Index)
        idx._docs = [
            "能天使的技能是扫射，攻击范围内所有敌人",
            "碎骨是重装敌人，血量高，防御强",
            "先锋干员费用低，适合开局部署",
        ]
        idx._ids = ["id1", "id2", "id3"]
        idx._metas = [
            {"source": "能天使", "type": "operator"},
            {"source": "碎骨", "type": "enemy"},
            {"source": "芬", "type": "operator"},
        ]
        idx._type_index = {"operator": [0, 2], "enemy": [1]}
        _inject_entity_dictionary(idx._metas)
        idx._bm25 = BM25Okapi([_tokenize(d) for d in idx._docs])
        return idx

    def test_search_returns_ranked(self):
        """检索返回按 BM25 分数降序，只返回分数>0的匹配文档。"""
        idx = self._make_small_index()
        hits = idx.search("能天使 技能", k=3)
        assert len(hits) >= 1
        assert hits[0]["metadata"]["source"] == "能天使"
        assert hits[0]["rank"] == 0
        # 分数降序
        for i in range(len(hits) - 1):
            assert hits[i]["score"] >= hits[i + 1]["score"]

    def test_search_doc_type_filter(self):
        """doc_type 过滤只返回指定类型。"""
        idx = self._make_small_index()
        hits = idx.search("敌人", k=10, doc_type="enemy")
        assert len(hits) == 1
        assert hits[0]["metadata"]["type"] == "enemy"

    def test_search_empty_query(self):
        """空 query 返回空列表。"""
        idx = self._make_small_index()
        assert idx.search("", k=5) == []

    def test_search_no_match(self):
        """无匹配返回空列表（用纯英文乱码，避免 jieba 切成常见中文词）。"""
        idx = self._make_small_index()
        hits = idx.search("zzzqqqxxx", k=5)
        assert hits == []

    def test_count(self):
        """count 返回文档数。"""
        idx = self._make_small_index()
        assert idx.count() == 3


# ---------------------------------------------------------------- Retriever 混合检索（mock 注入）
class TestRetrieverHybrid:
    def _make_mock_retriever(self, use_bm25=True):
        """构造注入 mock 组件的 Retriever（不依赖真实 ChromaDB/embedding）。"""
        ret = Retriever.__new__(Retriever)
        ret.top_k = 5
        ret.use_bm25 = use_bm25
        ret._bm25 = None  # 懒加载

        # mock embedder
        class MockEmbedder:
            def encode_query(self, q):
                return [0.1, 0.2, 0.3]
        ret.embedder = MockEmbedder()

        # mock store
        class MockStore:
            def query(self, vec, k=5, where=None):
                docs = [
                    {"document": "能天使的技能是扫射", "distance": 0.3,
                     "metadata": {"source": "能天使", "type": "operator"}},
                    {"document": "新约能天使的技能是强力扫射", "distance": 0.25,
                     "metadata": {"source": "新约能天使", "type": "operator"}},
                    {"document": "碎骨是重装敌人", "distance": 0.5,
                     "metadata": {"source": "碎骨", "type": "enemy"}},
                ]
                return docs[:k]
        ret.store = MockStore()
        return ret

    def test_hybrid_returns_top_k(self):
        """混合检索返回 Top-K 结果。"""
        ret = self._make_mock_retriever(use_bm25=False)  # 先测纯向量
        results = ret.search("能天使", k=2)
        assert len(results) == 2
        assert "content" in results[0]
        assert "score" in results[0]
        assert "metadata" in results[0]

    def test_explicit_named_rerank(self):
        """显式指名重排：问'能天使'时本体排在异格前面。"""
        meta_ben = {"source": "能天使", "type": "operator"}
        meta_alt = {"source": "新约能天使", "type": "operator"}
        assert _explicitly_named(meta_ben, "能天使的技能") is True
        # "新约能天使"包含"能天使"子串，但 query 没有明确说"新约能天使"
        # 注意：_explicitly_named 对中文做子串匹配，"新约能天使" in "能天使的技能" = False
        assert _explicitly_named(meta_alt, "能天使的技能") is False

    def test_stage_code_boundary(self):
        """关卡编号 ASCII 边界校验：'1-1' 不误命中 '11-1'。"""
        meta = {"source": "1-1 黑暗时代·上", "type": "stage"}
        assert _explicitly_named(meta, "11-1有哪些敌人") is False
        assert _explicitly_named(meta, "1-1有哪些敌人") is True

    def test_invalid_doc_type_raises(self):
        """非法 doc_type 抛 ValueError。"""
        ret = self._make_mock_retriever()
        with pytest.raises(ValueError):
            ret.search("test", doc_type="invalid_type")

    def test_bm25_disabled_fallback(self):
        """use_bm25=False 时走纯向量，不报错。显式指名重排把能天使排到 Top1。"""
        ret = self._make_mock_retriever(use_bm25=False)
        results = ret.search("能天使", k=3)
        assert len(results) == 3
        # 能天使被 query 显式指名，虽 distance=0.3 但重排到 Top1
        assert results[0]["metadata"]["source"] == "能天使"
        assert results[0]["score"] == round(1.0 - 0.3, 4)  # 0.7

    def test_rrf_k_constant(self):
        """RRF_K = 60（论文推荐值）。"""
        assert RRF_K == 60
