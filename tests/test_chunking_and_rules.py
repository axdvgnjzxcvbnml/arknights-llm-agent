# -*- coding: utf-8 -*-
"""审计 M6：build_rag 切分逻辑 + build_graph 克制规则 R1/R2/R3 的单元测试。

纯 CPU、不依赖真实 PRTS 语料：切分用内联 fixture 字典，规则用内联敌人记录。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from knowledge.graph.build_graph import derive_counter_rules  # noqa: E402
from knowledge.rag import build_rag  # noqa: E402


# ============================================================ build_rag 切分
class TestPackParagraphs:
    def test_packs_small_paragraphs_together(self):
        out = build_rag._pack_paragraphs(["a" * 10, "b" * 10], 100)
        assert out == ["a" * 10 + "\n" + "b" * 10]

    def test_splits_when_exceeding_max(self):
        out = build_rag._pack_paragraphs(["a" * 60, "b" * 60], 100)
        assert len(out) == 2 and all(len(x) <= 100 for x in out)

    def test_drops_blank_paragraphs(self):
        assert build_rag._pack_paragraphs(["", "   ", "x"], 100) == ["x"]

    def test_hard_wraps_oversized_sentence(self):
        long_sent = "字" * 250  # 无句读、超长，触发 max_chars 硬切兜底
        out = build_rag._pack_paragraphs([long_sent], 100)
        assert len(out) == 3 and all(len(x) <= 100 for x in out)
        assert "".join(out) == long_sent

    def test_respects_chinese_sentence_boundary(self):
        para = "第一句内容。第二句内容。第三句内容。"
        out = build_rag._pack_paragraphs([para], 12)
        assert all(len(x) <= 12 for x in out)
        assert "".join(out) == para.replace("。", "。")  # 内容（除分隔）不丢字


def _operator_fixture():
    return {
        "name": "测试干员",
        "meta": {
            "name": "测试干员", "star_rating": 5, "class": "狙击",
            "branch": "速射手", "pos": "高台", "tag": "输出 控场",
            "group": "测试势力",
        },
        "extra_attrs": {"初始部署费用": "12", "阻挡数": "1",
                        "再部署时间": "70", "攻击间隔": "1.0s"},
        "trait": {"分支": "速射手", "描述": "优先攻击空中单位。"},
        "obtain": {"公开招募": "是", "干员寻访": "是"},
        "growth_attrs": {"stages": ["精英0", "精英1"],
                          "rows": {"生命": [1000, 1200], "攻击": [300, 400]}},
        "skills": [
            {"name": "技能甲", "type": "攻击回复",
             "levels": [{"level": "1", "desc": "攻击力+10%", "initial": "0",
                         "cost": "20", "duration": "20"},
                        {"level": "10", "desc": "攻击力+50%", "initial": "0",
                         "cost": "20", "duration": "30"}]},
        ],
    }


class TestChunkOperator:
    def test_sections_and_metadata(self):
        chunks = build_rag.chunk_operator(_operator_fixture(), max_chars=500,
                                          source="测试干员")
        sections = {c["metadata"]["section"] for c in chunks}
        assert {"meta", "trait", "obtain", "attrs", "skill:技能甲"} <= sections
        for c in chunks:
            md = c["metadata"]
            assert md["type"] == "operator" and md["source"] == "测试干员"
            assert md["url"].endswith("%E6%B5%8B%E8%AF%95%E5%B9%B2%E5%91%98")
            assert c["text"].strip() and c["id"]
        # id 唯一
        ids = [c["id"] for c in chunks]
        assert len(ids) == len(set(ids))

    def test_skill_long_content_splits_with_context(self):
        data = _operator_fixture()
        # 造一条超长技能，强制分成多块，验证续块带上下文前缀且不超 max
        data["skills"] = [{
            "name": "超长技能", "type": "自动回复",
            "levels": [{"level": str(i), "desc": "效果说明" * 40} for i in range(8)],
        }]
        chunks = [c for c in build_rag.chunk_operator(data, max_chars=300,
                                                      source="测试干员")
                  if c["metadata"]["section"] == "skill:超长技能"]
        assert len(chunks) >= 2
        assert all(len(c["text"]) <= 300 for c in chunks)
        # 续块重复简短上下文
        assert all(c["text"].startswith("干员测试干员的技能「超长技能」（续）。")
                   for c in chunks[1:])

    def test_empty_operator_safe(self):
        # 空数据不报错：仅落一个 meta 头部块，不产出特性/技能等块
        chunks = build_rag.chunk_operator({}, max_chars=500, source="空")
        assert [c["metadata"]["section"] for c in chunks] == ["meta"]
        assert chunks[0]["metadata"]["source"] == "空"


# ============================================================ R1/R2/R3 规则
class TestCounterRules:
    RULES = {"high_defense_threshold": 800,
             "high_resistance_threshold": 50,
             "fast_speed_threshold": 2.0}

    def _ids(self, enemy):
        return [r[0] for r in derive_counter_rules(enemy, self.RULES)]

    def test_r1_high_defense(self):
        assert "R1_high_defense_to_arts" in self._ids({"defense": 900})
        assert "R1_high_defense_to_arts" in self._ids({"defense": 800})  # 边界 >=
        assert "R1_high_defense_to_arts" not in self._ids({"defense": 799})
        hit = next(r for r in derive_counter_rules({"defense": 900}, self.RULES)
                   if r[0] == "R1_high_defense_to_arts")
        # 职业克制 matcher 排第一、权重 1.0
        assert hit[2][0][0] == "is_caster" and hit[2][0][1] == "class"
        assert hit[2][0][2] == 1.0

    def test_r2_high_resistance(self):
        assert "R2_high_resistance_to_physical" in self._ids({"resistance": 60})
        assert "R2_high_resistance_to_physical" not in self._ids({"resistance": 49})
        hit = next(r for r in derive_counter_rules({"resistance": 70}, self.RULES)
                   if r[0] == "R2_high_resistance_to_physical")
        assert hit[2][0][0] == "is_physical_dps"

    def test_r3_fast_by_speed_or_keyword(self):
        assert "R3_fast_enemy_to_control" in self._ids({"speed": 2.5})
        assert "R3_fast_enemy_to_control" in self._ids({"desc": "高速移动单位"})
        assert "R3_fast_enemy_to_control" not in self._ids(
            {"speed": 1.0, "desc": "", "traits": ""})
        hit = next(r for r in derive_counter_rules({"speed": 3.0}, self.RULES)
                   if r[0] == "R3_fast_enemy_to_control")
        assert hit[2][0][0] == "has_control" and hit[2][0][2] == 0.6

    def test_rules_can_co_occur(self):
        ids = self._ids({"defense": 900, "resistance": 60, "speed": 3.0})
        assert ids == ["R1_high_defense_to_arts",
                       "R2_high_resistance_to_physical",
                       "R3_fast_enemy_to_control"]

    def test_weak_slow_enemy_has_no_rule(self):
        assert derive_counter_rules(
            {"defense": 100, "resistance": 0, "speed": 0.8,
             "desc": "", "traits": ""}, self.RULES) == []

    def test_missing_numeric_fields_safe(self):
        assert derive_counter_rules({}, self.RULES) == []
