"""练干员（干员培养）决策层：给培养优先级排序 + 理由（第十五批 任务二·3）。

输入：干员列表（练度/职业/标签/到下一阶段材料）+ 材料库存 + 当前关卡需求；
输出：按优先级降序的培养建议，每条带可读理由与 evidence 分级。

只决策，不操作（不碰 ADB）。纯 CPU，import 不拉 torch/numpy。

强度依据两档，严禁把占位规则说成事实：
- 没接强度榜时：职业/标签与关卡需求匹配 + 练度缺口 + 材料是否够，evidence=inferred:placeholder_rule；
- 接入血狼破军强度榜 JSON 后：tier 命中部分 evidence=retrieved:tier_list（榜单是外部观点，
  仍非"客观事实"，但比占位规则可信一档），其余因子仍是 placeholder_rule。
"""

import json
import os
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

__all__ = ["OperatorProfile", "StageNeed", "MaterialStock", "PriorityItem",
           "DevelopmentPlan", "OperatorDevelopmentAdvisor", "load_tier_list",
           "TIER_SCORE_DEFAULT", "EVIDENCE_PLACEHOLDER", "EVIDENCE_TIER"]

EVIDENCE_PLACEHOLDER = "inferred:placeholder_rule"
EVIDENCE_TIER = "retrieved:tier_list"

# 占位 tier -> 分值（接入真实榜单后可被覆盖）。tier 越小越强（T0 最强）。
TIER_SCORE_DEFAULT = {"T0": 40, "T1": 30, "T2": 20, "T3": 10}

DEFAULT_WEIGHTS = {
    "need_match": 50.0,    # 职业/标签与当前关卡需求匹配
    "power_gap": 30.0,     # 练度缺口（越值得补越高，但有封顶）
    "tier": 25.0,          # 强度榜加成（有榜单时）
    "material_ready": 15.0,  # 材料够立刻精英化/升级
}


class OperatorProfile(BaseModel):
    name: str
    profession: str = ""                 # 先锋/狙击/医疗/术师/重装/近卫/辅助/特种
    elite: int = Field(0, ge=0, le=2)    # 精英化阶段 0/1/2
    level: int = Field(1, ge=1, le=90)
    owned: bool = True
    tags: List[str] = Field(default_factory=list)
    # 到"下一培养阶段"所需材料 {material_id: count}，由调用方传入（不臆造）
    materials_to_next: Dict[str, int] = Field(default_factory=dict)
    target_elite: int = Field(2, ge=0, le=2)


class StageNeed(BaseModel):
    stage_id: str = ""
    # 当前关卡推荐的职业与职能标签（可来自 query_stage/recommend_operators）
    professions: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)   # 如 群体法术/对空/治疗/阻挡
    enemy_hints: List[str] = Field(default_factory=list)  # 如 高甲→需术师


class MaterialStock(BaseModel):
    materials: Dict[str, int] = Field(default_factory=dict)

    def covers(self, need: Dict[str, int]):
        return all(self.materials.get(k, 0) >= v for k, v in (need or {}).items())

    def missing(self, need: Dict[str, int]):
        return {k: v - self.materials.get(k, 0)
                for k, v in (need or {}).items() if self.materials.get(k, 0) < v}


class PriorityItem(BaseModel):
    name: str
    score: float
    rank: int = 0
    profession: str = ""
    reasons: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    materials_ready: bool = False
    materials_missing: Dict[str, int] = Field(default_factory=dict)
    owned: bool = True


class DevelopmentPlan(BaseModel):
    stage_id: str = ""
    items: List[PriorityItem] = Field(default_factory=list)  # 已按分数降序
    unowned_relevant: List[str] = Field(default_factory=list)  # 关卡需要但没拥有
    tier_source: str = ""   # 接入的强度榜标识（空=纯占位规则）
    notes: str = ""

    def top(self, k=5):
        return self.items[:k]


def load_tier_list(path):
    """加载血狼破军强度榜 JSON：{ "能天使": {"tier":"T0","score":..,"source":..}, ...}。

    文件缺失返回空 dict（调用方据此退回纯占位规则，不报错、不臆造）。
    """
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("强度榜 JSON 顶层需为映射 {干员: {tier,...}}")
    return data


class OperatorDevelopmentAdvisor(object):
    """培养优先级顾问。无 GPU，纯规则；tier_list 可选。"""

    def __init__(self, weights=None, tier_list=None, tier_source=""):
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        # tier_list: {name: {"tier": "T0"/"score": float}}
        self.tier_list = tier_list or {}
        self.tier_source = tier_source or ("" if not self.tier_list else "custom_tier_list")

    def _need_match(self, op, need):
        score, reasons, tags = 0.0, [], set()
        profs = set(need.professions or [])
        roles = set(need.roles or [])
        if op.profession and op.profession in profs:
            score += self.weights["need_match"] * 0.6
            reasons.append("职业「%s」正是本关推荐" % op.profession)
        overlap = roles.intersection(op.tags or [])
        if overlap:
            score += self.weights["need_match"] * 0.4
            reasons.append("具备本关需要的职能：%s" % "、".join(sorted(overlap)))
            tags.add(EVIDENCE_PLACEHOLDER)
        return score, reasons, tags

    def _power_gap(self, op):
        # 精英化缺口为主，等级缺口为辅；归一到 0..1 再乘权重，封顶 1。
        elite_gap = max(0, op.target_elite - op.elite)
        level_ratio = max(0.0, (op.target_elite and (60 - op.level) / 60.0) or 0.0)
        level_ratio = min(1.0, max(0.0, level_ratio))
        gap = min(1.0, elite_gap / 2.0 * 0.7 + level_ratio * 0.3)
        score = self.weights["power_gap"] * gap
        reasons = []
        if elite_gap > 0:
            reasons.append("精英化 %d→%d，有明确提升空间" % (op.elite, op.target_elite))
        if op.level < 60:
            reasons.append("等级 %d 偏低，升级收益高" % op.level)
        return score, reasons, {EVIDENCE_PLACEHOLDER} if reasons else set()

    def _tier(self, op):
        entry = self.tier_list.get(op.name)
        if not entry:
            return 0.0, [], set()
        if isinstance(entry, dict):
            tier = str(entry.get("tier", "")).upper()
            raw_score = entry.get("score")
        else:
            tier, raw_score = str(entry).upper(), None
        if raw_score is not None:
            score = float(raw_score)
        else:
            score = TIER_SCORE_DEFAULT.get(tier, 0.0)
        reason = "血狼破军强度榜评级 %s，泛用/强度加成" % tier if tier else \
            "强度榜给出评分 %.0f" % score
        return score, [reason], {EVIDENCE_TIER}

    def _materials(self, op, stock):
        ready = stock.covers(op.materials_to_next)
        missing = {} if ready else stock.missing(op.materials_to_next)
        if ready and op.materials_to_next:
            return self.weights["material_ready"], ["下一阶段材料齐备，可立即培养"], missing, True
        if not op.materials_to_next:
            return 0.0, ["未提供材料需求（占位，待补养成数据）"], missing, False
        return -5.0, ["材料不足，缺：%s" % "、".join(
            "%s×%d" % (k, v) for k, v in sorted(missing.items()))], missing, False

    def rank(self, operators, need=None, stock=None):
        # type: (List[OperatorProfile], StageNeed, MaterialStock) -> DevelopmentPlan
        need = need or StageNeed()
        stock = stock or MaterialStock()
        items, unowned = [], []
        for op in operators:
            if not op.owned:
                if (op.profession in set(need.professions or [])) or \
                        set(need.roles or []).intersection(op.tags or []):
                    unowned.append(op.name)
                continue
            score = 0.0
            reasons, evidence = [], set()
            s, r, t = self._need_match(op, need); score += s; reasons += r; evidence |= t
            s, r, t = self._power_gap(op); score += s; reasons += r; evidence |= t
            s, r, t = self._tier(op); score += s; reasons += r; evidence |= t
            ms, r, missing, ready = self._materials(op, stock)
            score += ms; reasons += r
            if not reasons:
                reasons.append("当前无明显培养紧迫性（占位规则）")
                evidence.add(EVIDENCE_PLACEHOLDER)
            items.append(PriorityItem(
                name=op.name, score=round(score, 2), profession=op.profession,
                reasons=reasons, evidence=sorted(evidence),
                materials_ready=ready, materials_missing=missing, owned=True))

        items.sort(key=lambda x: x.score, reverse=True)
        for i, it in enumerate(items, 1):
            it.rank = i
        return DevelopmentPlan(
            stage_id=need.stage_id, items=items,
            unowned_relevant=sorted(unowned), tier_source=self.tier_source,
            notes=("已接入强度榜：%s；tier 项为外部观点(retrieved)，匹配/缺口为占位推断(inferred)"
                   % self.tier_source) if self.tier_source
                  else "未接强度榜，全部为占位规则推断(inferred)，V100/数据就绪后替换")
