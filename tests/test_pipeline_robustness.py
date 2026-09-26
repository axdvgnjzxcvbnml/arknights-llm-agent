"""数据管线健壮性：RAG 切分边界测试。

其余模块（爬虫/图谱/SFT）的异常路径已由以下测试覆盖：
- tests/test_crawler.py（41 用例，含 HTML 缺字段/JS 对象异常/boss 布局）
- tests/test_chunking_and_rules.py（chunking + 克制规则 R1/R2/R3）
- tests/test_json_load_safe.py（JSON 加载容错）
- tests/test_build_rag_batch.py（批量构建边界）
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestRagChunkingRobustness(object):
    def test_chunk_very_long_text(self):
        """超长文本（~35000 字）切分不崩溃，chunk 不超过硬上限。"""
        from knowledge.rag.build_rag import _pack_paragraphs
        long_text = "这是一段很长的文本。" * 5000
        chunks = _pack_paragraphs([long_text], max_chars=500)
        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk) <= 550

    def test_chunk_special_characters(self):
        """含控制字符（null/0x01）的文本切分不崩溃。"""
        from knowledge.rag.build_rag import _pack_paragraphs
        weird_text = "正常文本\x00\x01包含控制字符\n\n第二段"
        chunks = _pack_paragraphs([weird_text], max_chars=500)
        assert len(chunks) >= 1

    def test_chunk_empty_paragraphs(self):
        """空段落列表返回空。"""
        from knowledge.rag.build_rag import _pack_paragraphs
        assert _pack_paragraphs([], max_chars=500) == []

    def test_chunk_operator_minimal(self):
        """只有 name 的干员 JSON 切分不崩溃。"""
        from knowledge.rag.build_rag import chunk_operator
        chunks = chunk_operator({"name": "测试干员"})
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_split_sentences_empty(self):
        """空文本分句不崩溃。"""
        from knowledge.rag.build_rag import _split_sentences
        assert _split_sentences("") == []
