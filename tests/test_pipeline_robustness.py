"""数据管线健壮性异常注入测试（基于实际函数签名）。

覆盖爬虫/RAG/图谱/SFT 四个模块的边界输入。
函数签名以实际代码为准：
- parse_operator(html) / parse_enemy(html) / parse_stage(html)
- extract_js_object(text, var_name)
- _pack_paragraphs(paragraphs, max_chars)
- chunk_operator(data, max_chars=500, source=None)
- derive_counter_rules(enemy, rules_cfg)
- _to_float(value) / _operator_signals(op) / _enemy_record_from_json(data)
- load_maa_job(path) / build_examples(job, ...) / is_generic_operator(name)
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# 1. 爬虫解析器异常注入
# ============================================================
class TestCrawlerRobustness(object):
    def test_operator_empty_html(self):
        from knowledge.crawler.parse_operators import parse_operator
        result = parse_operator("")
        assert result is not None
        assert isinstance(result, dict)

    def test_operator_missing_skill_table(self):
        from knowledge.crawler.parse_operators import parse_operator
        html = "<html><body><div>没有技能表格</div></body></html>"
        result = parse_operator(html)
        assert "skills" in result
        assert isinstance(result["skills"], list)

    def test_operator_garbage_html(self):
        from knowledge.crawler.parse_operators import parse_operator
        result = parse_operator("<<<not html>>>&&&")
        assert isinstance(result, dict)

    def test_enemy_empty_html(self):
        from knowledge.crawler.parse_enemies import parse_enemy
        result = parse_enemy("")
        assert result is not None
        assert "levels" in result

    def test_enemy_boss_special_layout(self):
        from knowledge.crawler.parse_enemies import parse_enemy
        html = "<html><body><h1>碎骨</h1><p>Boss 敌人，无标准级别表格</p></body></html>"
        result = parse_enemy(html)
        assert "levels" in result
        assert isinstance(result["levels"], list)

    def test_stage_empty_html(self):
        from knowledge.crawler.parse_stages import parse_stage
        result = parse_stage("")
        assert result is not None

    def test_stage_missing_enemy_table(self):
        from knowledge.crawler.parse_stages import parse_stage
        html = "<html><body><h1>3-8</h1><p>没有敌情表</p></body></html>"
        result = parse_stage(html)
        assert "enemies" in result or "modes" in result

    def test_js_object_trailing_comma(self):
        from knowledge.crawler._html_utils import extract_js_object
        js = "var charInfo = {name: '测试', star: 6,};"
        # 尾随逗号可能解析为空 dict 或部分结果，不崩溃即可
        obj = extract_js_object(js, "charInfo")
        assert isinstance(obj, dict)

    def test_js_object_single_quotes(self):
        from knowledge.crawler._html_utils import extract_js_object
        js = "var data = {'key': 'value', 'num': 42};"
        obj = extract_js_object(js, "data")
        assert isinstance(obj, dict)

    def test_js_object_unclosed(self):
        from knowledge.crawler._html_utils import extract_js_object
        js = "var bad = {name: '测试', star: 6"
        try:
            obj = extract_js_object(js, "bad")
            assert obj is None or isinstance(obj, dict)
        except Exception:
            pytest.fail("未闭合 JS 对象导致解析器崩溃")

    def test_js_object_not_found(self):
        from knowledge.crawler._html_utils import extract_js_object
        js = "var other = {a: 1};"
        obj = extract_js_object(js, "nonexistent")
        # 变量不存在时返回空 dict 或 None，不崩溃即可
        assert obj is None or isinstance(obj, dict)


# ============================================================
# 2. RAG 切分异常注入
# ============================================================
class TestRagRobustness(object):
    def test_chunk_very_long_text(self):
        from knowledge.rag.build_rag import _pack_paragraphs
        long_text = "这是一段很长的文本。" * 5000
        chunks = _pack_paragraphs([long_text], max_chars=500)
        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk) <= 550

    def test_chunk_special_characters(self):
        from knowledge.rag.build_rag import _pack_paragraphs
        weird_text = "正常文本\x00\x01包含控制字符\n\n第二段"
        chunks = _pack_paragraphs([weird_text], max_chars=500)
        assert len(chunks) >= 1

    def test_chunk_empty_paragraphs(self):
        from knowledge.rag.build_rag import _pack_paragraphs
        assert _pack_paragraphs([], max_chars=500) == []

    def test_chunk_operator_minimal(self):
        from knowledge.rag.build_rag import chunk_operator
        chunks = chunk_operator({"name": "测试干员"})
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_chunk_operator_empty(self):
        from knowledge.rag.build_rag import chunk_operator
        chunks = chunk_operator({})
        assert isinstance(chunks, list)

    def test_chunk_enemy_minimal(self):
        from knowledge.rag.build_rag import chunk_enemy
        chunks = chunk_enemy({"name": "测试敌人"})
        assert isinstance(chunks, list)

    def test_chunk_stage_minimal(self):
        from knowledge.rag.build_rag import chunk_stage
        chunks = chunk_stage({"stage_id": "9-9", "title": "测试"})
        assert isinstance(chunks, list)

    def test_split_sentences_empty(self):
        from knowledge.rag.build_rag import _split_sentences
        assert _split_sentences("") == []

    def test_split_sentences_only_punctuation(self):
        from knowledge.rag.build_rag import _split_sentences
        result = _split_sentences("。。。！？")
        assert isinstance(result, list)


# ============================================================
# 3. 图谱构建异常注入
# ============================================================
class TestGraphRobustness(object):
    def test_derive_counter_missing_defense(self):
        from knowledge.graph.build_graph import derive_counter_rules
        enemy = {"name": "敌人A"}
        rules_cfg = {"high_defense_threshold": 800, "high_resistance_threshold": 50,
                     "fast_speed_threshold": 2.0}
        try:
            rules = derive_counter_rules(enemy, rules_cfg)
            assert isinstance(rules, list)
        except Exception as e:
            pytest.fail("缺 defense 导致规则推导崩溃: %s" % e)

    def test_derive_counter_none_defense(self):
        from knowledge.graph.build_graph import derive_counter_rules
        enemy = {"name": "敌人A", "defense": None, "magic_resistance": None}
        rules_cfg = {"high_defense_threshold": 800, "high_resistance_threshold": 50,
                     "fast_speed_threshold": 2.0}
        rules = derive_counter_rules(enemy, rules_cfg)
        assert isinstance(rules, list)

    def test_derive_counter_high_defense(self):
        from knowledge.graph.build_graph import derive_counter_rules
        enemy = {"name": "高防敌人", "defense": 1000, "magic_resistance": 0}
        rules_cfg = {"high_defense_threshold": 800, "high_resistance_threshold": 50,
                     "fast_speed_threshold": 2.0}
        rules = derive_counter_rules(enemy, rules_cfg)
        assert isinstance(rules, list)
        # 高防敌人触发 R1 规则（matchers 里用 is_caster 标识术师）
        assert any("R1" in str(r) or "caster" in str(r).lower() for r in rules)

    def test_derive_counter_wrong_type_defense(self):
        """defense 为字符串时当前抛 TypeError（已知脆弱点，调用方应先 _to_float）。"""
        from knowledge.graph.build_graph import derive_counter_rules
        enemy = {"name": "敌人A", "defense": "很高", "magic_resistance": "0"}
        rules_cfg = {"high_defense_threshold": 800, "high_resistance_threshold": 50,
                     "fast_speed_threshold": 2.0}
        # 已知脆弱点：derive_counter_rules 内部直接比较，未做类型转换
        # 调用方应先用 _to_float 转换 defense/magic_resistance
        with pytest.raises((TypeError, Exception)):
            derive_counter_rules(enemy, rules_cfg)

    def test_to_float_invalid(self):
        from knowledge.graph.build_graph import _to_float
        # None/空串/非数字返回 None（调用方应 or 0 处理）
        assert _to_float(None) is None
        assert _to_float("") is None
        assert _to_float("not_a_number") is None
        # 有效数字正常转换
        assert _to_float("123") == 123.0
        assert _to_float(123) == 123.0

    def test_operator_signals_empty(self):
        from knowledge.graph.build_graph import _operator_signals
        signals = _operator_signals({})
        assert isinstance(signals, dict)

    def test_enemy_record_from_json_missing(self):
        """缺字段的敌人 JSON 转 record 返回空 dict（不崩溃）。"""
        from knowledge.graph.build_graph import _enemy_record_from_json
        record = _enemy_record_from_json({"name": "测试敌人"})
        assert isinstance(record, dict)


# ============================================================
# 4. SFT 数据准备异常注入
# ============================================================
class TestSftDataPrepRobustness(object):
    def test_load_empty_job(self, tmp_path):
        """空文件抛 JSONDecodeError（调用方应 try/except），不静默返回。"""
        import json
        from training.sft_data_prep import load_maa_job
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_maa_job(str(empty_file))

    def test_load_invalid_json(self, tmp_path):
        """非法 JSON 抛异常（调用方应处理）。"""
        import json
        from training.sft_data_prep import load_maa_job
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid,,,", encoding="utf-8")
        with pytest.raises((json.JSONDecodeError, Exception)):
            load_maa_job(str(bad_file))

    def test_load_nonexistent_file(self):
        """不存在的文件抛 FileNotFoundError（调用方应处理）。"""
        from training.sft_data_prep import load_maa_job
        with pytest.raises((FileNotFoundError, Exception)):
            load_maa_job("/nonexistent/path/job.json")

    def test_build_examples_empty_job(self):
        """空作业不崩溃（返回 tuple 或 list）。"""
        from training.sft_data_prep import build_examples
        try:
            result = build_examples({})
            assert isinstance(result, (list, tuple))
        except Exception as e:
            pytest.fail("空作业导致 build_examples 崩溃: %s" % e)

    def test_build_examples_missing_actions(self):
        """作业缺 actions 字段不崩溃。"""
        from training.sft_data_prep import build_examples
        job = {"stage": "3-8", "title": "测试作业"}
        try:
            result = build_examples(job)
            assert isinstance(result, (list, tuple))
        except Exception as e:
            pytest.fail("缺 actions 导致崩溃: %s" % e)

    def test_build_examples_null_actions(self):
        """作业 actions 为 None 不崩溃。"""
        from training.sft_data_prep import build_examples
        job = {"stage": "3-8", "actions": None}
        try:
            result = build_examples(job)
            assert isinstance(result, (list, tuple))
        except Exception as e:
            pytest.fail("actions=None 导致崩溃: %s" % e)

    def test_is_generic_operator_edge(self):
        from training.sft_data_prep import is_generic_operator
        assert isinstance(is_generic_operator(""), bool)
        assert isinstance(is_generic_operator(None), bool)
        assert isinstance(is_generic_operator("弦惊"), bool)
        assert isinstance(is_generic_operator("煌"), bool)

    def test_loc_text_invalid(self):
        from training.sft_data_prep import _loc_text
        assert isinstance(_loc_text(None), str)
        assert isinstance(_loc_text([]), str)
        assert isinstance(_loc_text([0, 0]), str)
        assert isinstance(_loc_text("not_a_list"), str)
