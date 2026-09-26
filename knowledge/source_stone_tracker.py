"""源石获取策略（第十五批，任务二·1）：根据关卡进度估算还能拿多少首通源石。

明日方舟的源石（至纯源石）主要来自主线关卡：
- 每个主线普通关**首次通关**得 1 源石；
- 有"突袭模式"的关卡，突袭首通再得 1 源石（需先通普通）。

本模块只做**确定性台账计算**（不联网、不爬用户账号）：
- 输入玩家进度：普通首通集合、突袭首通集合（+ 当前持有源石，可选）；
- 输出已获得 / 还能拿的源石，按普通/突袭拆分，并给出接下来可刷的关卡顺序；
- 同时给 Agent 抽卡决策用的一段自然语言摘要（render_for_prompt）。

数据来源与证据：
- "哪些关存在/是否有突袭"来自本地 PRTS 关卡 JSON（data/prts_raw/stages，**gitignore**），
  属 fact:prts；"每关 1 源石"是游戏规则常量（rule，可在配置覆盖）；
- 玩家"通关了哪些关"是调用方传入的运行时事实（fact:user_progress）；
- "还能拿多少 / 抽完还剩多少"是据规则**推算**（inferred:calculated），不是账号实测。

import 本模块仅用标准库。
"""

import glob
import json
import os
import re
from dataclasses import asdict, dataclass, field

__all__ = ["StageStone", "StoneProgress", "SourceStoneReport", "SourceStoneTracker",
           "main_stage_order", "DEFAULT_STAGES_DIR"]

DEFAULT_STAGES_DIR = os.path.join("data", "prts_raw", "stages")
_MAIN_CODE_RE = re.compile(r"^(\d+)-(\d+)$")


def main_stage_order(code):
    # type: (str) -> tuple
    """主线关排序键 (chapter, index)；非标准 code 排到最后。"""
    m = _MAIN_CODE_RE.match(str(code))
    if not m:
        return (10 ** 6, str(code))
    return (int(m.group(1)), int(m.group(2)))


@dataclass
class StageStone(object):
    stage_id: str           # 关卡编号，如 "3-8"
    title: str = ""
    has_raid: bool = False  # 是否有突袭模式（多 1 源石）
    normal_stone: int = 1
    raid_stone: int = 1

    def total_stone(self):
        return self.normal_stone + (self.raid_stone if self.has_raid else 0)


@dataclass
class StoneProgress(object):
    earned_normal: int = 0
    earned_raid: int = 0
    remaining_normal: int = 0
    remaining_raid: int = 0

    @property
    def earned(self):
        return self.earned_normal + self.earned_raid

    @property
    def remaining(self):
        return self.remaining_normal + self.remaining_raid

    def to_dict(self):
        return asdict(self)


@dataclass
class SourceStoneReport(object):
    progress: StoneProgress
    remaining_stages: list = field(default_factory=list)  # 还能拿源石的关卡（按章节排序）
    locked_raid_stages: list = field(default_factory=list)  # 突袭可拿但普通未首通
    current_stone: int = 0       # 当前持有（调用方传入，可为 0=未知）
    stone_per_normal: int = 1
    stone_per_raid: int = 1

    @property
    def total_earned_from_stages(self):
        return self.progress.earned

    @property
    def total_remaining(self):
        return self.progress.remaining

    @property
    def projected_after_collect(self):
        """剩余首通全拿完后的持有源石（当前未知即按 0 起算的增量）。"""
        return self.current_stone + self.progress.remaining

    def to_dict(self):
        return {
            "progress": self.progress.to_dict(),
            "total_earned_from_stages": self.total_earned_from_stages,
            "total_remaining": self.total_remaining,
            "current_stone": self.current_stone,
            "projected_after_collect": self.projected_after_collect,
            "remaining_stages": list(self.remaining_stages),
            "locked_raid_stages": list(self.locked_raid_stages),
            "stone_per_normal": self.stone_per_normal,
            "stone_per_raid": self.stone_per_raid,
        }


class SourceStoneTracker(object):
    """主线首通源石台账。纯计算，stages 由调用方或本地 PRTS 目录提供。"""

    def __init__(self, stages=None, stone_per_normal=1, stone_per_raid=1):
        # stages: dict stage_id -> StageStone（或可转成它的映射）
        self.stages = {}
        for sid, st in (stages or {}).items():
            self.stages[str(sid)] = st if isinstance(st, StageStone) else StageStone(
                stage_id=str(sid),
                title=str((st or {}).get("title", "")),
                has_raid=bool((st or {}).get("has_raid", False)))
        self.stone_per_normal = int(stone_per_normal)
        self.stone_per_raid = int(stone_per_raid)

    # ---------------- 构建 ----------------
    @classmethod
    def from_prts_dir(cls, stages_dir=DEFAULT_STAGES_DIR,
                      stone_per_normal=1, stone_per_raid=1):
        """从 data/prts_raw/stages/*.json 构建主线台账。

        只收 code 形如 "章节-序号" 的主线关；有 raid 信息块则视为有突袭。
        目录缺失时给明确报错（数据不入库，需先跑爬虫；不臆造关卡）。
        """
        if not os.path.isdir(stages_dir):
            raise FileNotFoundError(
                "关卡目录不存在: %s。请先运行爬虫（scripts/crawl_prts.sh）生成 PRTS 数据，"
                "或用 SourceStoneTracker(stages=...) 直接传入关卡表。" % stages_dir)
        stages = {}
        for path in sorted(glob.glob(os.path.join(stages_dir, "*.json"))):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            code = str(d.get("code", "")).strip()
            if not _MAIN_CODE_RE.match(code):
                continue  # 活动关/支线/磨难等不计入主线首通源石台账
            stages[code] = StageStone(
                stage_id=code,
                title=str(d.get("name", "")),
                has_raid=bool(d.get("raid")),
                normal_stone=stone_per_normal,
                raid_stone=stone_per_raid)
        return cls(stages, stone_per_normal, stone_per_raid)

    def __len__(self):
        return len(self.stages)

    # ---------------- 计算 ----------------
    def analyze(self, completed_normal=None, completed_raid=None, current_stone=0):
        # type: (object, object, int) -> SourceStoneReport
        completed_normal = {str(x) for x in (completed_normal or [])}
        completed_raid = {str(x) for x in (completed_raid or [])}
        current_stone = int(current_stone or 0)

        earned_n = earned_r = remain_n = remain_r = 0
        remaining_stages = []
        locked_raid = []

        for sid in sorted(self.stages.keys(), key=main_stage_order):
            st = self.stages[sid]
            normal_done = sid in completed_normal
            raid_done = sid in completed_raid

            if normal_done:
                earned_n += self.stone_per_normal
            else:
                remain_n += self.stone_per_normal

            if st.has_raid:
                if raid_done:
                    earned_r += self.stone_per_raid
                else:
                    # 突袭源石只要没拿就计入"潜在剩余"，无论是否被普通首通卡住；
                    # 是否"可立即打"由 locked_raid_stages 区分。
                    remain_r += self.stone_per_raid
                    if normal_done:
                        # 普通已通、突袭未通：可直接打
                        remaining_stages.append({
                            "stage_id": sid, "title": st.title,
                            "normal_pending": False, "raid_pending": True,
                            "stone": self.stone_per_raid})
                    else:
                        # 突袭奖励存在但被普通首通卡住：单列，避免当成"立刻可拿"
                        locked_raid.append(sid)

            if not normal_done:
                entry = {
                    "stage_id": sid, "title": st.title,
                    "normal_pending": True,
                    "raid_pending": bool(st.has_raid and not raid_done),
                    "stone": self.stone_per_normal
                             + (self.stone_per_raid if st.has_raid and not raid_done else 0),
                }
                remaining_stages.append(entry)

        prog = StoneProgress(
            earned_normal=earned_n, earned_raid=earned_r,
            remaining_normal=remain_n, remaining_raid=remain_r)
        return SourceStoneReport(
            progress=prog,
            remaining_stages=remaining_stages,
            locked_raid_stages=locked_raid,
            current_stone=current_stone,
            stone_per_normal=self.stone_per_normal,
            stone_per_raid=self.stone_per_raid)

    # ---------------- 抽卡决策用摘要 ----------------
    def render_for_prompt(self, report, next_k=5, planned_pulls=0,
                          orundum_per_pull=600, stone_to_orundum=180):
        # type: (SourceStoneReport, int, int, int, int) -> str
        """生成给抽卡决策 Prompt 的自然语言源石信息。

        planned_pulls：计划抽的次数；1 抽约 600 合成玉，1 源石约换 180 合成玉，
        据此粗算"抽完这波后，剩余首通源石折合还能补多少抽 / 还缺多少"（inferred）。
        """
        p = report.progress
        lines = [
            "[源石台账·首通获取] 已通过首通获得约 %d 源石（普通 %d + 突袭 %d，fact:规则推算）。"
            % (p.earned, p.earned_normal, p.earned_raid),
            "尚未拿到的首通源石共 %d：普通首通 %d + 突袭首通 %d（inferred:calculated）。"
            % (p.remaining, p.remaining_normal, p.remaining_raid),
        ]
        if report.locked_raid_stages:
            lines.append("其中 %d 个关卡的突袭源石需先通关普通才解锁（如 %s）。"
                         % (len(report.locked_raid_stages),
                            "、".join(report.locked_raid_stages[:3])))
        upcoming = [x["stage_id"] for x in report.remaining_stages[:next_k]]
        if upcoming:
            lines.append("接下来可刷的关卡（按章节）：%s。" % "、".join(upcoming))
        if planned_pulls > 0:
            need_orundum = planned_pulls * orundum_per_pull
            extra_orundum = p.remaining * stone_to_orundum
            cover_pulls = extra_orundum // orundum_per_pull
            gap = max(0, need_orundum - extra_orundum)
            lines.append(
                "计划抽 %d 抽约需 %d 合成玉；剩余首通源石全拿约折 %d 合成玉（≈%d 抽），"
                "缺口约 %d 合成玉（按 1源石=%d玉 粗算，inferred，仅供抽卡决策参考）。"
                % (planned_pulls, need_orundum, extra_orundum, cover_pulls,
                   gap, stone_to_orundum))
        lines.append("注：源石台账为规则推算，非账号实时数据；是否抽卡请结合持有合成玉与井线。")
        return "\n".join(lines)
