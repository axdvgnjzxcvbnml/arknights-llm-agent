"""strategy 练干员培养决策单元测试（第十五批 任务二·3）。纯 CPU，占位规则 + tier 端口。"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from strategy import (  # noqa: E402
    OperatorProfile, StageNeed, MaterialStock,
    OperatorDevelopmentAdvisor, load_tier_list,
    EVIDENCE_PLACEHOLDER, EVIDENCE_TIER)


def _caster(name, **kw):
    base = dict(profession="术师", elite=0, level=1, target_elite=2,
                tags=["群体法术", "AoE"])
    base.update(kw)
    return OperatorProfile(name=name, **base)


class TestRanking:
    def test_need_match_puts_caster_first(self):
        need = StageNeed(stage_id="3-8", professions=["术师"], roles=["群体法术"])
        ops = [
            OperatorProfile(name="能天使", profession="狙击", elite=1, level=70,
                            target_elite=2, tags=["对空", "速射"]),
            _caster("阿米娅"),
        ]
        plan = OperatorDevelopmentAdvisor().rank(ops, need)
        assert plan.items[0].name == "阿米娅"
        assert plan.items[0].rank == 1
        assert any("术师" in r for r in plan.items[0].reasons)
        assert plan.stage_id == "3-8"

    def test_scores_descending_and_ranks_assigned(self):
        need = StageNeed(professions=["术师"], roles=["群体法术"])
        ops = [_caster("C%d" % i, level=1 + 15 * i) for i in range(3)]
        plan = OperatorDevelopmentAdvisor().rank(ops, need)
        scores = [it.score for it in plan.items]
        assert scores == sorted(scores, reverse=True)
        assert [it.rank for it in plan.items] == [1, 2, 3]

    def test_material_ready_beats_missing(self):
        need = StageNeed(professions=["术师"], roles=["群体法术"])
        ready = _caster("成型术师", materials_to_next={"chip": 5})
        poor = _caster("缺料术师", materials_to_next={"chip": 9})
        stock = MaterialStock(materials={"chip": 5})
        plan = OperatorDevelopmentAdvisor().rank([poor, ready], need, stock)
        assert plan.items[0].name == "成型术师"
        assert plan.items[0].materials_ready is True
        poor_item = next(i for i in plan.items if i.name == "缺料术师")
        assert poor_item.materials_ready is False
        assert poor_item.materials_missing == {"chip": 4}
        assert any("材料不足" in r for r in poor_item.reasons)

    def test_unowned_relevant_listed_not_ranked(self):
        need = StageNeed(professions=["医疗"], roles=["治疗"])
        owned = [OperatorProfile(name="嘉维尔", profession="医疗", elite=0, level=40,
                                 target_elite=2, tags=["治疗"])]
        missing = OperatorProfile(name="夜莺", profession="医疗", owned=False,
                                  tags=["治疗", "群奶"])
        plan = OperatorDevelopmentAdvisor().rank(owned + [missing], need)
        assert [i.name for i in plan.items] == ["嘉维尔"]
        assert plan.unowned_relevant == ["夜莺"]


class TestTierAndEvidence:
    def test_tier_breaks_tie_and_evidence_labeled(self):
        need = StageNeed(professions=["术师"], roles=["群体法术"])
        a = _caster("普通术师")
        b = _caster("榜单术师")
        tier = {"榜单术师": {"tier": "T0"}}
        plan = OperatorDevelopmentAdvisor(tier_list=tier,
                                          tier_source="bloodwolf_tier_demo").rank([a, b], need)
        assert plan.items[0].name == "榜单术师"
        assert EVIDENCE_TIER in plan.items[0].evidence
        assert any("T0" in r for r in plan.items[0].reasons)
        assert plan.tier_source == "bloodwolf_tier_demo"
        # 未上榜者不带 retrieved tier 证据
        other = next(i for i in plan.items if i.name == "普通术师")
        assert EVIDENCE_TIER not in other.evidence

    def test_without_tier_all_placeholder(self):
        need = StageNeed(professions=["术师"])
        plan = OperatorDevelopmentAdvisor().rank([_caster("X")], need)
        ev = set().union(*[set(i.evidence) for i in plan.items])
        assert ev == {EVIDENCE_PLACEHOLDER}
        assert "占位" in plan.notes

    def test_explicit_score_tier_used(self):
        need = StageNeed(professions=["术师"])
        tier = {"高分术师": {"score": 35.0}}
        plan = OperatorDevelopmentAdvisor(
            tier_list=tier, tier_source="t").rank([_caster("高分术师")], need)
        assert EVIDENCE_TIER in plan.items[0].evidence


class TestTierLoader:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_tier_list(str(tmp_path / "nope.json")) == {}
        assert load_tier_list("") == {}

    def test_load_valid_json(self, tmp_path):
        p = tmp_path / "tier.json"
        p.write_text(json.dumps({"能天使": {"tier": "T0"}}), encoding="utf-8")
        data = load_tier_list(str(p))
        assert data["能天使"]["tier"] == "T0"
