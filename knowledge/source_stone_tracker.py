"""源石获取策略（第十五批，任务二·1）：根据关卡进度估算还能拿多少首通源石。

明日方舟的源石（至纯源石）主要来自主线关卡：
- 每个主线普通关**首次通关**得 1 源石；
- 有"突袭模式"的关卡，突袭首通再得 1 源石（需先通普通）。

本模块只做**确定性台账计算**（不联网、不爬用户账号）：
- 输入玩家进度：普通首通集合、突袭首通集合（+ 当前持有源石，可选）；
- 输出已获得 / 还能拿的源石，按普通/突袭拆分，并给出接下来可刷的关卡顺序；
- 剩余源石再按"到手时间"分三档：
  1. 立即可拿：已解锁、未通关的普通关（前置关已通）+ 已解锁未打的突袭；
  2. 短期可拿：当前进度后 short_term_window 关内、1-2 天可推进的普通关及其突袭（估算）；
  3. 长期可拿：更远的高难关与未解锁突袭——只用于总资源规划，**不进抽卡决策 Prompt**；
- render_for_prompt（抽卡决策）只看前两档，避免模型高估短期补源石能力而给出激进抽卡建议。

数据来源与证据：
- "哪些关存在/是否有突袭"来自本地 PRTS 关卡 JSON（data/prts_raw/stages，**gitignore**），
  属 fact:prts；"每关 1 源石"是游戏规则常量（rule，可在配置覆盖）；
- 玩家"通关了哪些关"是调用方传入的运行时事实（fact:user_progress）；
- 分档（尤其短期/长期边界）是无难度数据下的窗口估算（inferred:estimated），
  "还能拿多少 / 抽完还剩多少"是据规则**推算**（inferred:calculated），不是账号实测。

import 本模块仅用标准库。
"""

import glob
import json
import os
import re
from dataclasses import asdict, dataclass, field

__all__ = ["StageStone", "StoneProgress", "SourceStoneReport", "SourceStoneTracker",
           "main_stage_order", "DEFAULT_STAGES_DIR", "DEFAULT_SHORT_TERM_WINDOW",
           "TIER_IMMEDIATE", "TIER_SHORT_TERM", "TIER_LONG_TERM"]

DEFAULT_STAGES_DIR = os.path.join("data", "prts_raw", "stages")
_MAIN_CODE_RE = re.compile(r"^(\d+)-(\d+)$")

# 剩余源石到手时间分档
TIER_IMMEDIATE = "immediate"   # 立即可拿
TIER_SHORT_TERM = "short_term"  # 短期可拿（1-2 天，窗口估算）
TIER_LONG_TERM = "long_term"    # 长期可拿（高难/未解锁，仅总资源规划）

# 默认把"当前进度之后、连续 N 关内能推进"的普通关算作短期（无难度数据的窗口近似）
DEFAULT_SHORT_TERM_WINDOW = 6


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


def _empty_tier():
    """一档剩余源石：普通/突袭拆分 + 关卡明细。"""
    return {"normal_stone": 0, "raid_stone": 0, "stages": []}


@dataclass
class SourceStoneReport(object):
    progress: StoneProgress
    remaining_stages: list = field(default_factory=list)  # 还能拿源石的关卡（按章节排序）
    locked_raid_stages: list = field(default_factory=list)  # 突袭可拿但普通未首通
    tiers: dict = field(default_factory=dict)  # immediate/short_term/long_term 三档
    short_term_window: int = DEFAULT_SHORT_TERM_WINDOW
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

    def tier_stone(self, name):
        t = self.tiers.get(name) or {}
        return int(t.get("normal_stone", 0)) + int(t.get("raid_stone", 0))

    @property
    def prompt_decision_stone(self):
        """抽卡决策可用源石：**仅立即可拿 + 短期可拿**，不含长期高难/未解锁。"""
        return self.tier_stone(TIER_IMMEDIATE) + self.tier_stone(TIER_SHORT_TERM)

    @property
    def long_term_stone(self):
        """长期可拿源石（仅总资源规划，禁止进抽卡决策 Prompt）。"""
        return self.tier_stone(TIER_LONG_TERM)

    def to_dict(self):
        return {
            "progress": self.progress.to_dict(),
            "total_earned_from_stages": self.total_earned_from_stages,
            "total_remaining": self.total_remaining,
            "current_stone": self.current_stone,
            "projected_after_collect": self.projected_after_collect,
            "prompt_decision_stone": self.prompt_decision_stone,
            "long_term_stone": self.long_term_stone,
            "remaining_stages": list(self.remaining_stages),
            "locked_raid_stages": list(self.locked_raid_stages),
            "tiers": {k: {"normal_stone": v["normal_stone"],
                          "raid_stone": v["raid_stone"],
                          "stages": list(v["stages"])}
                      for k, v in self.tiers.items()},
            "short_term_window": self.short_term_window,
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
    def analyze(self, completed_normal=None, completed_raid=None, current_stone=0,
                short_term_window=DEFAULT_SHORT_TERM_WINDOW):
        # type: (object, object, int, int) -> SourceStoneReport
        completed_normal = {str(x) for x in (completed_normal or [])}
        completed_raid = {str(x) for x in (completed_raid or [])}
        current_stone = int(current_stone or 0)
        short_term_window = max(0, int(short_term_window))

        earned_n = earned_r = remain_n = remain_r = 0
        remaining_stages = []
        locked_raid = []

        ordered = sorted(self.stages.keys(), key=main_stage_order)
        prev_of = {sid: (ordered[i - 1] if i > 0 else None)
                   for i, sid in enumerate(ordered)}

        # 普通关三档分类（按主线线性顺序的窗口近似）
        pending_normals = [sid for sid in ordered if sid not in completed_normal]
        immediate_normals = [sid for sid in pending_normals
                             if prev_of[sid] is None or prev_of[sid] in completed_normal]
        rest_normals = [sid for sid in pending_normals if sid not in immediate_normals]
        short_normals = rest_normals[:short_term_window]
        long_normals = rest_normals[short_term_window:]
        normal_tier = {}
        for sid in immediate_normals:
            normal_tier[sid] = TIER_IMMEDIATE
        for sid in short_normals:
            normal_tier[sid] = TIER_SHORT_TERM
        for sid in long_normals:
            normal_tier[sid] = TIER_LONG_TERM

        tiers = {TIER_IMMEDIATE: _empty_tier(),
                 TIER_SHORT_TERM: _empty_tier(),
                 TIER_LONG_TERM: _empty_tier()}

        def _add_stage(tier, sid, title, kind, stone):
            tiers[tier]["stages"].append(
                {"stage_id": sid, "title": title, "kind": kind, "stone": int(stone)})

        for sid in ordered:
            st = self.stages[sid]
            normal_done = sid in completed_normal
            raid_done = sid in completed_raid
            raid_pending = st.has_raid and not raid_done

            if normal_done:
                earned_n += self.stone_per_normal
            else:
                remain_n += self.stone_per_normal
                # 该普通首通源石归到对应档
                nt = normal_tier[sid]
                tiers[nt]["normal_stone"] += self.stone_per_normal
                _add_stage(nt, sid, st.title, "normal", self.stone_per_normal)

            if st.has_raid:
                if raid_done:
                    earned_r += self.stone_per_raid
                else:
                    # 突袭源石只要没拿就计入"潜在剩余"，无论是否被普通首通卡住。
                    remain_r += self.stone_per_raid
                    if normal_done:
                        # 普通已通、突袭未通：立即可打
                        tiers[TIER_IMMEDIATE]["raid_stone"] += self.stone_per_raid
                        _add_stage(TIER_IMMEDIATE, sid, st.title, "raid", self.stone_per_raid)
                        remaining_stages.append({
                            "stage_id": sid, "title": st.title,
                            "normal_pending": False, "raid_pending": True,
                            "tier": TIER_IMMEDIATE, "stone": self.stone_per_raid})
                    else:
                        # 突袭被普通首通卡住：跟着普通关的档位走（普通在短期窗口内，
                        # 突袭也按"1-2 天可拿"的短期估算；普通属长期则突袭也是长期）。
                        rt = normal_tier.get(sid, TIER_LONG_TERM)
                        if rt == TIER_IMMEDIATE:
                            rt = TIER_SHORT_TERM
                        tiers[rt]["raid_stone"] += self.stone_per_raid
                        _add_stage(rt, sid, st.title, "raid", self.stone_per_raid)
                        locked_raid.append(sid)

            if not normal_done:
                entry = {
                    "stage_id": sid, "title": st.title,
                    "normal_pending": True,
                    "raid_pending": bool(raid_pending),
                    "tier": normal_tier[sid],
                    "stone": self.stone_per_normal
                             + (self.stone_per_raid if raid_pending else 0),
                }
                remaining_stages.append(entry)

        prog = StoneProgress(
            earned_normal=earned_n, earned_raid=earned_r,
            remaining_normal=remain_n, remaining_raid=remain_r)
        return SourceStoneReport(
            progress=prog,
            remaining_stages=remaining_stages,
            locked_raid_stages=locked_raid,
            tiers=tiers,
            short_term_window=short_term_window,
            current_stone=current_stone,
            stone_per_normal=self.stone_per_normal,
            stone_per_raid=self.stone_per_raid)

    # ---------------- 抽卡决策用摘要（仅前两档，保守） ----------------
    def render_for_prompt(self, report, next_k=5, planned_pulls=0,
                          orundum_per_pull=600, stone_to_orundum=180):
        # type: (SourceStoneReport, int, int, int, int) -> str
        """生成给抽卡决策 Prompt 的自然语言源石信息。

        **只给模型看"立即可拿 + 短期可拿(1-2天)"两档**，不提供长期高难/未解锁总量，
        防止模型高估短期补源石能力、做出"抽完很快能补回"的激进决策。

        planned_pulls：计划抽的次数；1 抽约 600 合成玉，1 源石约换 180 合成玉，
        据此用**短期决策源石**粗算"抽完这波短期内能补多少抽 / 还缺多少"（inferred）。
        """
        p = report.progress
        imm = report.tiers.get(TIER_IMMEDIATE) or _empty_tier()
        sh = report.tiers.get(TIER_SHORT_TERM) or _empty_tier()
        imm_n, imm_r = imm["normal_stone"], imm["raid_stone"]
        sh_n, sh_r = sh["normal_stone"], sh["raid_stone"]
        decision_stone = report.prompt_decision_stone

        lines = [
            "[源石台账·首通获取] 已通过首通获得约 %d 源石（普通 %d + 突袭 %d，fact:规则推算）。"
            % (p.earned, p.earned_normal, p.earned_raid),
            "本次抽卡决策只计算短期能到手的源石，共约 %d（inferred:calculated）："
            % decision_stone,
            "  1) 立即可拿（已解锁未通关普通/已解锁突袭）：%d（普通 %d + 突袭 %d）。"
            % (imm_n + imm_r, imm_n, imm_r),
            "  2) 短期可拿（约1-2天内可推进的连续 %d 关，估算 inferred:estimated）："
            " %d（普通 %d + 突袭 %d）。"
            % (report.short_term_window, sh_n + sh_r, sh_n, sh_r),
        ]
        # 同一关卡可能同时有普通/突袭两条，展示时按关卡去重保序
        _seen = set()
        upcoming = []
        for s in (imm["stages"] + sh["stages"]):
            if s["stage_id"] not in _seen:
                _seen.add(s["stage_id"])
                upcoming.append(s["stage_id"])
        upcoming = upcoming[:next_k]
        if upcoming:
            lines.append("短期优先可刷：%s。" % "、".join(upcoming))
        if planned_pulls > 0:
            need_orundum = planned_pulls * orundum_per_pull
            extra_orundum = decision_stone * stone_to_orundum
            cover_pulls = extra_orundum // orundum_per_pull
            gap = max(0, need_orundum - extra_orundum)
            lines.append(
                "计划抽 %d 抽约需 %d 合成玉；按短期可拿的 %d 源石约折 %d 合成玉（≈%d 抽），"
                "短期缺口约 %d 合成玉（1源石=%d玉 粗算，inferred，仅供保守决策参考）。"
                % (planned_pulls, need_orundum, decision_stone, extra_orundum,
                   cover_pulls, gap, stone_to_orundum))
        lines.append(
            "注：更远的高难关卡与未解锁突袭源石不计入本次抽卡决策（避免高估短期回血）；"
            "台账为规则估算、非账号实时数据，请结合持有合成玉与井线谨慎决策，不鼓励充值。")
        return "\n".join(lines)

    # ---------------- 总资源规划摘要（含第三档，仅用于 Dashboard/长期规划） ----------------
    def render_resource_overview(self, report):
        # type: (SourceStoneReport) -> str
        """总资源规划视图：三档全列。**禁止**直接喂给抽卡决策 Prompt。"""
        p = report.progress
        return "\n".join([
            "[源石总资源规划] 已获首通 %d（普通 %d + 突袭 %d）；剩余首通共 %d（普通 %d + 突袭 %d）。"
            % (p.earned, p.earned_normal, p.earned_raid,
               p.remaining, p.remaining_normal, p.remaining_raid),
            "  立即可拿 %d；短期(1-2天) %d；长期(高难/未解锁突袭) %d。"
            % (report.tier_stone(TIER_IMMEDIATE),
               report.tier_stone(TIER_SHORT_TERM),
               report.tier_stone(TIER_LONG_TERM)),
            "提示：长期档仅用于总资源规划，不进入抽卡决策（决策只看立即可拿+短期）。",
        ])
