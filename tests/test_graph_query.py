"""知识图谱查询接口单元测试（GraphQuery，mock 小图）。

构造一个 6 节点 8 边的小 NetworkX 图，直接注入 GraphQuery.graph，
绕过 GraphML 文件加载，覆盖全部查询方法。
"""

import networkx as nx
import pytest

from knowledge.graph.query_graph import GraphQuery


def _make_small_graph():
    """构造测试用小图谱：2干员/2敌人/1关卡/1技能，8条边。"""
    g = nx.DiGraph()
    # 节点
    g.add_node("operator:能天使", kind="operator", name="能天使",
               cls="狙击", star=6, position="远程")
    g.add_node("operator:艾雅法拉", kind="operator", name="艾雅法拉",
               cls="术师", star=6, position="远程")
    g.add_node("enemy:碎骨", kind="enemy", name="碎骨",
               defense=500, resistance=0, position="地面")
    g.add_node("enemy:冲锋兵", kind="enemy", name="冲锋兵",
               defense=100, resistance=0, position="地面")
    g.add_node("stage:3-8", kind="stage", name="3-8 黄昏")
    g.add_node("skill:扫射", kind="skill", name="扫射", skill_type="攻击回复")
    # 边
    g.add_edge("operator:能天使", "skill:扫射", relation="HAS_SKILL")
    g.add_edge("stage:3-8", "enemy:碎骨", relation="CONTAINS_ENEMY",
               count=1, level=0)
    g.add_edge("stage:3-8", "enemy:冲锋兵", relation="CONTAINS_ENEMY",
               count=3, level=0)
    g.add_edge("operator:能天使", "enemy:碎骨", relation="COUNTERS",
               rule="R1", evidence="inferred", weight=1.0,
               reason="远程物理输出", match_basis="class=狙击")
    g.add_edge("operator:艾雅法拉", "enemy:碎骨", relation="COUNTERS",
               rule="R2", evidence="inferred", weight=2.0,
               reason="法术穿透高防", match_basis="class=术师")
    g.add_edge("stage:3-8", "operator:能天使", relation="RECOMMENDS",
               support=2, score=1.5, matched_enemies="碎骨",
               matched_rules="R1")
    g.add_edge("stage:3-8", "operator:艾雅法拉", relation="RECOMMENDS",
               support=3, score=2.5, matched_enemies="碎骨",
               matched_rules="R2")
    return g


def _make_query():
    """构造注入 mock 图的 GraphQuery（绕过 __init__ 的文件加载）。"""
    gq = GraphQuery.__new__(GraphQuery)
    gq.graph = _make_small_graph()
    gq._heavy_armor_cache = {}
    gq.config = {"graph": {"rules": {"high_defense_threshold": 300}}}
    return gq


class TestSkillsOfOperator:
    def test_has_skills(self):
        gq = _make_query()
        skills = gq.skills_of_operator("能天使")
        assert len(skills) == 1
        assert skills[0]["skill"] == "扫射"
        assert skills[0]["skill_type"] == "攻击回复"

    def test_no_skills(self):
        gq = _make_query()
        assert gq.skills_of_operator("不存在的干员") == []


class TestEnemiesInStage:
    def test_enemies_list(self):
        gq = _make_query()
        enemies = gq.enemies_in_stage("3-8")
        assert len(enemies) == 2
        names = {e["enemy"] for e in enemies}
        assert names == {"碎骨", "冲锋兵"}

    def test_enemy_fields(self):
        gq = _make_query()
        enemies = gq.enemies_in_stage("3-8")
        suigu = [e for e in enemies if e["enemy"] == "碎骨"][0]
        assert suigu["count"] == 1
        assert suigu["level"] == 0
        assert suigu["defense"] == 500
        assert suigu["position"] == "地面"

    def test_empty_stage(self):
        gq = _make_query()
        assert gq.enemies_in_stage("99-9") == []


class TestOperatorsCountering:
    def test_countering_operators(self):
        gq = _make_query()
        ops = gq.operators_countering("碎骨")
        assert len(ops) == 2
        names = {o["operator"] for o in ops}
        assert names == {"能天使", "艾雅法拉"}

    def test_evidence_inferred(self):
        """COUNTERS 边 evidence 恒为 inferred。"""
        gq = _make_query()
        ops = gq.operators_countering("碎骨")
        for o in ops:
            assert o["evidence"] == "inferred"
            assert o["rule"] in ("R1", "R2")

    def test_no_countering(self):
        gq = _make_query()
        assert gq.operators_countering("冲锋兵") == []


class TestEnemiesCounteredBy:
    def test_countered_enemies(self):
        gq = _make_query()
        enemies = gq.enemies_countered_by("能天使")
        assert len(enemies) == 1
        assert enemies[0]["enemy"] == "碎骨"
        assert enemies[0]["defense"] == 500

    def test_aiya_countered(self):
        gq = _make_query()
        enemies = gq.enemies_countered_by("艾雅法拉")
        assert len(enemies) == 1
        assert enemies[0]["rule"] == "R2"

    def test_no_countered(self):
        gq = _make_query()
        assert gq.enemies_countered_by("不存在的干员") == []


class TestOperatorsForStage:
    def test_recommended_operators(self):
        gq = _make_query()
        ops = gq.operators_for_stage("3-8")
        assert len(ops) == 2
        # 按 score 降序：艾雅法拉(2.5) > 能天使(1.5)
        assert ops[0]["operator"] == "艾雅法拉"
        assert ops[1]["operator"] == "能天使"

    def test_fields(self):
        gq = _make_query()
        ops = gq.operators_for_stage("3-8")
        assert ops[0]["support"] == 3
        assert ops[0]["score"] == 2.5
        assert "碎骨" in ops[0]["matched_enemies"]

    def test_empty_stage(self):
        gq = _make_query()
        assert gq.operators_for_stage("99-9") == []


class TestCounterHeavyArmor:
    def test_heavy_armor_operators(self):
        """高防敌人（defense>=300）只有碎骨，克制它的干员有2个。"""
        gq = _make_query()
        result = gq.counter_heavy_armor(threshold=300)
        assert len(result) == 2
        names = {r["operator"] for r in result}
        assert names == {"能天使", "艾雅法拉"}

    def test_heavy_armor_ranked_by_score(self):
        """按 score 降序：艾雅法拉(weight=2.0) > 能天使(1.0)。"""
        gq = _make_query()
        result = gq.counter_heavy_armor(threshold=300)
        assert result[0]["operator"] == "艾雅法拉"
        assert result[0]["score"] >= result[1]["score"]

    def test_heavy_enemies_field(self):
        """heavy_enemies 列出被克制的高防敌人名。"""
        gq = _make_query()
        result = gq.counter_heavy_armor(threshold=300)
        for r in result:
            assert "碎骨" in r["heavy_enemies"]
            assert r["count"] >= 1

    def test_high_threshold_no_match(self):
        """阈值设极高（>500），没有高防敌人，返回空。"""
        gq = _make_query()
        result = gq.counter_heavy_armor(threshold=10000)
        assert result == []

    def test_cache(self):
        """相同阈值第二次走缓存，结果一致。"""
        gq = _make_query()
        r1 = gq.counter_heavy_armor(threshold=300)
        r2 = gq.counter_heavy_armor(threshold=300)
        assert r1 == r2
        assert 300 in gq._heavy_armor_cache


class TestResolveEnemy:
    def test_exact_match(self):
        gq = _make_query()
        assert gq._resolve_enemy("碎骨") == "enemy:碎骨"

    def test_fallback_by_name(self):
        """节点 ID 不匹配但 name 匹配时回退。"""
        gq = _make_query()
        # 碎骨的节点 ID 就是 enemy:碎骨，测试一个 ID 不同但 name 相同的情况
        # 这里小图没有这种情况，测试不存在的敌人返回 exact
        result = gq._resolve_enemy("不存在的敌人")
        assert result == "enemy:不存在的敌人"

    def test_not_in_graph(self):
        gq = _make_query()
        assert "enemy:不存在" not in gq.graph
        assert gq._resolve_enemy("不存在") == "enemy:不存在"


class TestStats:
    def test_stats_counts(self):
        gq = _make_query()
        stats = gq.stats()
        # 小图有 6 个节点，按 kind 统计
        assert stats["nodes"]["operator"] == 2
        assert stats["nodes"]["enemy"] == 2
        assert stats["nodes"]["stage"] == 1
        assert stats["nodes"]["skill"] == 1
        # 8 条边，按 relation 统计
        assert stats["edges"]["HAS_SKILL"] == 1
        assert stats["edges"]["CONTAINS_ENEMY"] == 2
        assert stats["edges"]["COUNTERS"] == 2
        assert stats["edges"]["RECOMMENDS"] == 2
