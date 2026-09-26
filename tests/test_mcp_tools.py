"""MCP 工具单元测试。

分三层，保证在无数据/无模型的 CI 环境也能安全运行：
1. TestSchemas / TestBoundaries：只验证 Pydantic 契约与边界安全，恒跑（不依赖数据/模型）；
2. TestRealData：依赖 data/prts_raw JSON 与 data/graph 图谱，缺失则 skip；
3. TestRAGRetrieval：依赖 data/vector_store 向量库（加载 bge），缺失则 skip。

运行：
    python -m pytest tests/test_mcp_tools.py -v
"""

import json
import os
from pathlib import Path

import pytest

# 无论从哪个工作目录启动 pytest，都切到项目根，保证 configs/、data/ 相对路径有效
ROOT = Path(__file__).resolve().parents[1]
os.chdir(str(ROOT))

from knowledge.mcp_tools import (  # noqa: E402
    query_enemy,
    query_operator,
    query_skill,
    query_stage,
    recommend_operators,
    search_guide,
)
from knowledge.mcp_tools import schemas as S  # noqa: E402

HAS_OPERATOR = (ROOT / "data/prts_raw/operators/能天使.json").exists()
HAS_STAGE = (ROOT / "data/prts_raw/stages/3-8 黄昏.json").exists()
HAS_GRAPH = (ROOT / "data/graph/arknights_graph.graphml").exists()
HAS_VECTOR_STORE = (ROOT / "data/vector_store/chroma.sqlite3").exists()


# ============================ 1. 数据契约（恒跑） ============================

class TestSchemas:
    def test_operator_class_alias(self):
        d = S.OperatorOut(found=True, evidence=S.EVIDENCE_FACT,
                          operator_class="术师").model_dump(by_alias=True)
        assert d["class"] == "术师"            # 对外 JSON 用 class
        assert "operator_class" not in d

    def test_guide_hit_type_alias(self):
        d = S.GuideHit(content="x", score=0.5, source="s").model_dump(by_alias=True)
        assert d["type"] in ("operator", "enemy", "stage", "guide", "")
        assert "doc_type" not in d

    def test_evidence_enum(self):
        from pydantic import ValidationError
        # L2：基础 fact 输出的 evidence 必填，漏传即校验失败，不静默退回 fact
        with pytest.raises(ValidationError):
            S.OperatorOut(found=True)
        assert S.OperatorOut(found=True, evidence="fact").evidence == "fact"
        assert S.RecommendOut(found=False, stage_id="x").evidence == "inferred"
        rec = S.RecommendedOperator(operator="x")
        assert rec.evidence == "inferred"      # 推荐项默认推断
        # RAG 检索结果恒为 retrieved（参考资料，非事实判断）
        hit = S.GuideHit(content="x", score=1.0, source="s")
        assert hit.evidence == "retrieved"
        assert S.GuideOut(found=True, query="q").evidence == "retrieved"
        assert S.EVIDENCE_RETRIEVED == "retrieved"

    def test_constraints_defaults(self):
        c = S.RecommendConstraints()
        assert c.top_n == 8 and c.classes is None

    def test_constraints_bounds_reject_out_of_range_star(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            S.RecommendConstraints(min_star=99)  # 星级上限 6
        with pytest.raises(ValidationError):
            S.RecommendIn(stage_id="x", constraints={"top_n": 99})  # top_n 上限 30

    def test_models_are_json_serializable(self):
        d = S.OperatorOut(found=True, evidence=S.EVIDENCE_FACT, name="能天使",
                          operator_class="狙击",
                          star_rating=6).model_dump(by_alias=True)
        json.dumps(d, ensure_ascii=False)  # 不抛即通过


# ============================ 2. 边界安全（恒跑，不加载重资源） ============================

class TestBoundaries:
    def test_empty_and_blank_inputs(self):
        assert query_operator("").found is False
        assert query_operator("   ").found is False
        assert query_stage("").found is False
        assert query_enemy("").found is False
        assert query_skill("能天使", "").found is False
        assert query_skill("", "过载模式").found is False

    def test_nonexistent_entities(self):
        assert query_operator("不存在的干员zzz").found is False
        assert query_enemy("不存在的敌人zzz").found is False
        assert query_stage("99-9").found is False

    def test_enemy_bad_level_type(self):
        r = query_enemy("碎骨", level="不是数字")
        assert r.found is False and "level" in r.message

    def test_search_empty_and_bad_params_does_not_load_model(self):
        assert search_guide("   ").found is False       # 空 query 不应触发 bge 加载
        assert search_guide("x", k=0).found is False     # k 越界
        assert search_guide("x", k=100).found is False
        assert search_guide("x", doc_type="bad").found is False  # 非法类型

    def test_recommend_bad_constraints_does_not_load_graph(self):
        assert recommend_operators("4-7", {"min_star": 99}).found is False
        assert recommend_operators("4-7", "not-a-dict").found is False
        assert recommend_operators("").found is False


# ============================ 3. 真实数据（需已爬取 JSON / 已建图谱） ============================

@pytest.mark.skipif(not HAS_OPERATOR, reason="缺少 data/prts_raw 干员 JSON")
class TestOperatorReal:
    def test_exusiai_full_info(self):
        o = query_operator("能天使")
        assert o.found and o.evidence == "fact"
        assert o.operator_class == "狙击" and o.star_rating == 6
        assert o.branch == "速射手" and o.deploy_cost
        assert [s.name for s in o.skills] == ["冲锋模式", "扫射模式", "过载模式"]
        assert o.trait is not None and "空中" in o.trait.desc
        assert o.source_url.startswith("https://prts.wiki/w/")

    def test_variant_form_is_distinct(self):
        a = query_operator("阿米娅(近卫)")
        assert a.found and a.operator_class == "近卫"
        assert len(a.skills) == 2

    def test_skill_detail_exact_and_fuzzy_and_missing(self):
        s = query_skill("能天使", "过载模式")
        assert s.found and s.skill.name == "过载模式" and len(s.skill.levels) == 10
        fuzzy = query_skill("能天使", "过载")
        assert fuzzy.found and fuzzy.skill.name == "过载模式"
        missing = query_skill("能天使", "不存在的技能")
        assert missing.found is False and "过载模式" in missing.message


@pytest.mark.skipif(not HAS_OPERATOR, reason="缺少 data/prts_raw 敌人 JSON")
class TestEnemyReal:
    def test_bonebreaker_by_level(self):
        e = query_enemy("碎骨")
        assert e.found and e.evidence == "fact"
        assert len(e.levels) >= 2
        lv0 = e.levels[0]
        assert lv0.position == "领袖" and "最大生命值" in lv0.attrs
        one = query_enemy("碎骨", level=1)
        assert one.found and len(one.levels) == 1
        bad = query_enemy("碎骨", level=99)
        assert bad.found is False


@pytest.mark.skipif(not HAS_STAGE, reason="缺少 data/prts_raw 关卡 JSON")
class TestStageReal:
    def test_stage_3_8(self):
        st = query_stage("3-8")
        assert st.found and st.evidence == "fact" and st.stage_id == "3-8"
        assert len(st.enemies) == 8
        assert any(e.name == "碎骨" and e.level == "1" for e in st.enemies)
        assert st.info.get("初始COST") == "10"


# ============================ 推荐（inferred，需图谱） ============================

@pytest.mark.skipif(not (HAS_GRAPH and HAS_STAGE), reason="缺少图谱或关卡数据")
class TestRecommendReal:
    def test_recommend_is_inferred_with_rules_and_note(self):
        r = recommend_operators("4-7")
        assert r.found and r.evidence == "inferred" and r.operators
        for op in r.operators:
            assert op.evidence == "inferred"
            assert op.matched_rules and op.score > 0
        assert "inferred" in r.note

    def test_constraint_class_filter(self):
        r = recommend_operators("4-7", {"classes": ["狙击"], "top_n": 10})
        assert r.found and r.operators
        assert all(op.operator_class == "狙击" for op in r.operators)

    def test_top_n_limit(self):
        r = recommend_operators("4-7", {"top_n": 2})
        assert len(r.operators) == 2

    def test_class_with_no_counter_yields_empty(self):
        # 医疗不会因"物理克高抗"规则被推荐，过滤后应为空但 found=True
        r = recommend_operators("4-7", {"classes": ["医疗"]})
        assert r.found and r.operators == [] and r.message

    def test_stage_without_weakness_empty(self):
        # 3-8 敌人未达阈值：有信息量的空推荐（区别于关卡不存在）
        r = recommend_operators("3-8")
        assert r.found and r.operators == []

    def test_missing_stage(self):
        assert recommend_operators("99-9").found is False


# ============================ 4. RAG 检索（需向量库） ============================

@pytest.mark.skipif(not HAS_VECTOR_STORE, reason="缺少 data/vector_store 向量库")
class TestRAGRetrieval:
    def test_exusiai_skill_query(self):
        r = search_guide("能天使的技能是什么", k=5)
        assert r.found and r.embedding_backend == "bge" and r.hits
        assert r.evidence == "retrieved" and r.note
        top = r.hits[0]
        assert top.source == "能天使"
        assert top.section.startswith("skill")
        # 命中片段也是 retrieved：参考资料而非事实判断
        assert top.evidence == "retrieved" and top.url.startswith("https://prts.wiki/w/")

    def test_type_filter(self):
        r = search_guide("碎骨的属性", k=5, doc_type="enemy")
        assert r.found and all(h.doc_type == "enemy" for h in r.hits)
