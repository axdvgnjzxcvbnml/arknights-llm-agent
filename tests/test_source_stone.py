"""knowledge/source_stone_tracker.py 单元测试（第十五批 任务二·1 + 第十六批三档口径）。

合成关卡台账恒跑（不依赖 PRTS 数据）；from_prts_dir 用例在无本地数据时 skip（CI 无 data/）。
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from knowledge.source_stone_tracker import (  # noqa: E402
    SourceStoneTracker, StageStone, main_stage_order, DEFAULT_STAGES_DIR,
    DEFAULT_SHORT_TERM_WINDOW,
    TIER_IMMEDIATE, TIER_SHORT_TERM, TIER_LONG_TERM)


def _stages():
    # 3-1/3-2 有突袭，3-3 无突袭
    return {
        "3-1": StageStone("3-1", "3-1", has_raid=True),
        "3-2": StageStone("3-2", "3-2", has_raid=True),
        "3-3": StageStone("3-3", "3-3", has_raid=False),
    }


def _tier_sum(r):
    return sum(r.tier_stone(t) for t in
               (TIER_IMMEDIATE, TIER_SHORT_TERM, TIER_LONG_TERM))


class TestStoneMath:
    def test_fresh_account_all_remaining(self):
        t = SourceStoneTracker(_stages())
        r = t.analyze()
        # 普通 3 + 突袭 2（仅 3-1/3-2）= 5
        assert r.progress.remaining_normal == 3
        assert r.progress.remaining_raid == 2
        assert r.progress.earned == 0 and r.total_remaining == 5
        # 突袭都被普通卡住，进 locked
        assert sorted(r.locked_raid_stages) == ["3-1", "3-2"]
        # 三档加总必须守恒
        assert _tier_sum(r) == 5

    def test_three_tier_partition_fresh(self):
        # 新号：3-1 是第一关（无前置）→立即可拿；3-2/3-3 在短期窗口内；无长期
        r = SourceStoneTracker(_stages()).analyze()
        imm = r.tiers[TIER_IMMEDIATE]
        sh = r.tiers[TIER_SHORT_TERM]
        lo = r.tiers[TIER_LONG_TERM]
        assert imm["normal_stone"] == 1 and imm["raid_stone"] == 0
        # 3-1 突袭跟着普通走进短期；3-2 普通+突袭、3-3 普通
        assert sh["normal_stone"] == 2 and sh["raid_stone"] == 2
        assert lo["normal_stone"] == 0 and lo["raid_stone"] == 0
        assert r.prompt_decision_stone == 5 and r.long_term_stone == 0

    def test_partial_progress(self):
        t = SourceStoneTracker(_stages())
        # 3-1 普通+突袭都通；3-2 只通普通；3-3 未动
        r = t.analyze(completed_normal=["3-1", "3-2"],
                      completed_raid=["3-1"], current_stone=4)
        assert r.progress.earned_normal == 2
        assert r.progress.earned_raid == 1
        # 剩余：普通 3-3(1)；突袭 3-2(1，普通已通可直接打)
        assert r.progress.remaining_normal == 1
        assert r.progress.remaining_raid == 1
        assert r.total_remaining == 2
        assert r.projected_after_collect == 6  # 当前4 + 剩余2
        # 两者都已解锁 → 全在立即可拿档
        assert r.tier_stone(TIER_IMMEDIATE) == 2
        assert r.tier_stone(TIER_SHORT_TERM) == 0
        assert r.prompt_decision_stone == 2

    def test_raid_locked_counts_as_total_but_not_direct(self):
        t = SourceStoneTracker(_stages())
        r = t.analyze(completed_normal=["3-3"])  # 只通无突袭的 3-3
        # 3-1/3-2 普通未通：各 1 普通 + 1 突袭（潜在但锁定）；3-3 已清
        assert r.progress.remaining_normal == 2
        assert r.progress.remaining_raid == 2    # 潜在未拿（虽被普通卡住）
        assert r.total_remaining == 4
        assert sorted(r.locked_raid_stages) == ["3-1", "3-2"]
        # "可直接刷"的剩余关只有两条普通待通关（无 raid_pending=True 的直取项）
        direct_raid = [x for x in r.remaining_stages if not x["normal_pending"]]
        assert direct_raid == []
        assert _tier_sum(r) == 4

    def test_long_term_excluded_from_decision(self):
        # 10 个连续无突袭关、新号、窗口=6：立即1 + 短期6 + 长期3
        stages = {("10-%d" % i): StageStone("10-%d" % i) for i in range(1, 11)}
        t = SourceStoneTracker(stages)
        r = t.analyze(short_term_window=6)
        assert r.tier_stone(TIER_IMMEDIATE) == 1
        assert r.tier_stone(TIER_SHORT_TERM) == 6
        assert r.tier_stone(TIER_LONG_TERM) == 3
        assert r.prompt_decision_stone == 7          # 决策只看 1+6
        assert r.prompt_decision_stone + r.long_term_stone == r.total_remaining == 10
        # 窗口参数生效
        r2 = t.analyze(short_term_window=0)
        assert r2.tier_stone(TIER_IMMEDIATE) == 1
        assert r2.tier_stone(TIER_SHORT_TERM) == 0
        assert r2.tier_stone(TIER_LONG_TERM) == 9

    def test_remaining_stages_ordered_by_chapter(self):
        stages = {"10-1": StageStone("10-1"), "2-9": StageStone("2-9"),
                  "1-12": StageStone("1-12")}
        r = SourceStoneTracker(stages).analyze()
        ids = [x["stage_id"] for x in r.remaining_stages]
        assert ids == ["1-12", "2-9", "10-1"]

    def test_unknown_progress_ids_ignored(self):
        r = SourceStoneTracker(_stages()).analyze(completed_normal=["99-9"])
        assert r.progress.earned_normal == 0

    def test_render_contains_ledger_and_pull_math(self):
        t = SourceStoneTracker(_stages())
        rpt = t.analyze(current_stone=10)
        text = t.render_for_prompt(rpt, planned_pulls=10)
        # 小号台账短期决策源石=5，折 900 玉，10 抽缺口 5100
        assert "共约 5" in text
        assert "计划抽 10 抽" in text and "6000 合成玉" in text
        assert "短期缺口约 5100 合成玉" in text
        assert "inferred" in text
        # 必须有分档，且不能出现"全拿"式长期口径
        assert "立即可拿" in text and "短期可拿" in text
        assert "全拿" not in text

    def test_render_omits_long_term_numbers(self):
        stages = {("10-%d" % i): StageStone("10-%d" % i) for i in range(1, 11)}
        t = SourceStoneTracker(stages)
        text = t.render_for_prompt(t.analyze(short_term_window=6), next_k=0)
        # 决策量 7 出现；长期档 3 的数字不得出现在抽卡 Prompt
        assert "共约 7" in text
        assert "3" not in text
        overview = t.render_resource_overview(t.analyze(short_term_window=6))
        assert "长期(高难/未解锁突袭) 3" in overview

    def test_render_without_planned_pulls(self):
        t = SourceStoneTracker(_stages())
        text = t.render_for_prompt(t.analyze())
        assert "计划抽" not in text and "立即可拿" in text

    def test_to_dict_has_tiers(self):
        d = SourceStoneTracker(_stages()).analyze().to_dict()
        assert set(["immediate", "short_term", "long_term"]).issubset(d["tiers"])
        assert d["prompt_decision_stone"] == 5

    def test_main_stage_order(self):
        assert main_stage_order("3-8") < main_stage_order("3-10")
        assert main_stage_order("2-1") < main_stage_order("10-1")
        assert main_stage_order("活动X")[0] > 1000

    def test_default_window_constant(self):
        assert DEFAULT_SHORT_TERM_WINDOW == 6


class TestFromPrtsDir:
    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SourceStoneTracker.from_prts_dir(str(tmp_path / "nope"))

    @pytest.mark.skipif(not os.path.isdir(DEFAULT_STAGES_DIR),
                        reason="本地无 PRTS 关卡数据（CI 不爬数据）")
    def test_build_from_real_prts_dir(self):
        t = SourceStoneTracker.from_prts_dir(DEFAULT_STAGES_DIR)
        assert len(t) >= 200  # 主线关数量级（当前全量约 288）
        r = t.analyze()
        # 全新账号：普通剩余 == 关卡数；突袭潜在剩余 == 有突袭关数（全被普通首通卡住）
        assert r.progress.remaining_normal == len(t)
        n_raid = sum(1 for s in t.stages.values() if s.has_raid)
        assert r.progress.remaining_raid == n_raid
        assert len(r.locked_raid_stages) == n_raid
        # 三档守恒；新号立即可拿=首关普通(+首关突袭若有)，长期必须为大头
        assert _tier_sum(r) == r.total_remaining
        assert r.tier_stone(TIER_LONG_TERM) > r.tier_stone(TIER_SHORT_TERM)
        assert r.prompt_decision_stone < r.total_remaining
