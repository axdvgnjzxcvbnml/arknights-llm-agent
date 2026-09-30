# -*- coding: utf-8 -*-
"""
Stage 3 规划层——方案评分。

输入：候选方案 + 当前状态
输出：每个方案的评分（拦截覆盖率、费用效率、风险）

设计原则：
- 无状态纯函数
- 评分维度：拦截覆盖率（0.4）+ 费用效率（0.3）+ 风险控制（0.3）
- 输出 0~1 的综合评分，越高越好
"""
from typing import Dict, List, Optional, Tuple

from perception.schemas import StateTensor
from planner.plan_generator import DeployPlan


class PlanScore:
    """方案评分结果。"""

    def __init__(
        self,
        plan_id: int,
        total_score: float,
        coverage_score: float,
        cost_efficiency: float,
        risk_score: float,
        details: Dict[str, float],
    ):
        self.plan_id = plan_id
        self.total_score = total_score  # 0~1 综合评分
        self.coverage_score = coverage_score  # 拦截覆盖率
        self.cost_efficiency = cost_efficiency  # 费用效率
        self.risk_score = risk_score  # 风险控制（越高风险越低）
        self.details = details

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "total_score": round(self.total_score, 3),
            "coverage": round(self.coverage_score, 3),
            "cost_efficiency": round(self.cost_efficiency, 3),
            "risk": round(self.risk_score, 3),
            "details": {k: round(v, 3) for k, v in self.details.items()},
        }


def _coverage_score(plan: DeployPlan) -> float:
    """
    拦截覆盖率评分（0~1）。

    直接使用 plan.coverage（路径覆盖率），已经是 0~1。
    """
    return min(1.0, max(0.0, plan.coverage))


def _cost_efficiency_score(
    plan: DeployPlan,
    state_tensor: StateTensor,
) -> float:
    """
    费用效率评分（0~1）。

    维度：
    1. 费用利用率：实际费用 / 可用费用（不超预算加分）
    2. 单位费用覆盖率：coverage / total_cost（费用越低效率越高）
    3. 部署数量效率：action_count / max_possible（部署越多越好，但不绝对）
    """
    current_cost = state_tensor.scalars.cost
    total_cost = plan.total_cost
    coverage = plan.coverage
    action_count = len(plan.actions)

    # 1. 费用利用率（0.4权重）：不超当前费用得满分，超了扣分
    if current_cost > 0:
        utilization = min(1.0, total_cost / current_cost) if total_cost <= current_cost else max(0.0, 1.0 - (total_cost - current_cost) / 10.0)
    else:
        utilization = 0.5  # 无费用信息时给中性分

    # 2. 单位费用覆盖率（0.4权重）
    if total_cost > 0 and coverage > 0:
        per_cost_coverage = min(1.0, coverage / (total_cost / 10.0))  # 每10费覆盖100%得满分
    else:
        per_cost_coverage = 0.0

    # 3. 部署数量（0.2权重）：至少1个得基础分，4个以上满分
    deploy_score = min(1.0, action_count / 4.0) if action_count > 0 else 0.0

    score = 0.4 * utilization + 0.4 * per_cost_coverage + 0.2 * deploy_score
    return min(1.0, max(0.0, score))


def _risk_score(
    plan: DeployPlan,
    state_tensor: StateTensor,
) -> float:
    """
    风险控制评分（0~1，越高风险越低）。

    维度：
    1. 高台比例：远程干员放高台更安全（高台不被地面敌人攻击）
    2. 医疗覆盖：有医疗干员降低风险
    3. 费用余量：部署后剩余费用越多，应对突发能力越强
    4. 部署数量风险：部署过少可能漏怪，过多可能费用溢出
    """
    current_cost = state_tensor.scalars.cost
    total_cost = plan.total_cost
    action_count = len(plan.actions)

    # 1. 高台比例（0.3权重）：骨架阶段无法判断干员位置是否高台，给中性分
    # TODO-V100: 接入地图张量判断部署位置是否高台
    highland_ratio = 0.5

    # 2. 医疗覆盖（0.2权重）：骨架阶段无法判断是否有医疗，给中性分
    # TODO-V100: 接入干员职业判断
    medical_coverage = 0.5

    # 3. 费用余量（0.3权重）：剩余费用越多越好
    if current_cost > 0:
        remaining = max(0.0, current_cost - total_cost)
        cost_margin = min(1.0, remaining / current_cost)
    else:
        cost_margin = 0.5

    # 4. 部署数量风险（0.2权重）：2-4个最优，过少或过多扣分
    if 2 <= action_count <= 4:
        deploy_risk = 1.0
    elif action_count == 1:
        deploy_risk = 0.6
    elif action_count == 0:
        deploy_risk = 0.0
    else:
        deploy_risk = 0.7  # 5个以上可能费用溢出

    score = (
        0.3 * highland_ratio
        + 0.2 * medical_coverage
        + 0.3 * cost_margin
        + 0.2 * deploy_risk
    )
    return min(1.0, max(0.0, score))


def score_plan(
    plan: DeployPlan,
    state_tensor: StateTensor,
    weights: Optional[Dict[str, float]] = None,
) -> PlanScore:
    """
    为单个方案评分。

    Args:
        plan: 候选方案
        state_tensor: 当前状态张量
        weights: 评分维度权重（默认 coverage:0.4, cost:0.3, risk:0.3）

    Returns:
        PlanScore: 评分结果
    """
    if weights is None:
        weights = {"coverage": 0.4, "cost": 0.3, "risk": 0.3}

    cov = _coverage_score(plan)
    cost_eff = _cost_efficiency_score(plan, state_tensor)
    risk = _risk_score(plan, state_tensor)

    total = (
        weights.get("coverage", 0.4) * cov
        + weights.get("cost", 0.3) * cost_eff
        + weights.get("risk", 0.3) * risk
    )

    details = {
        "coverage_raw": cov,
        "cost_efficiency_raw": cost_eff,
        "risk_raw": risk,
        "total_cost": plan.total_cost,
        "action_count": len(plan.actions),
        "plan_coverage": plan.coverage,
    }

    return PlanScore(
        plan_id=plan.plan_id,
        total_score=min(1.0, max(0.0, total)),
        coverage_score=cov,
        cost_efficiency=cost_eff,
        risk_score=risk,
        details=details,
    )


def score_all_plans(
    plans: List[DeployPlan],
    state_tensor: StateTensor,
    weights: Optional[Dict[str, float]] = None,
) -> List[PlanScore]:
    """
    为所有方案评分，按综合评分降序排列。
    """
    scores = [score_plan(plan, state_tensor, weights) for plan in plans]
    scores.sort(key=lambda s: s.total_score, reverse=True)
    return scores


def best_plan(
    plans: List[DeployPlan],
    state_tensor: StateTensor,
    weights: Optional[Dict[str, float]] = None,
) -> Optional[PlanScore]:
    """
    返回评分最高的方案。如果没有方案返回 None。
    """
    scores = score_all_plans(plans, state_tensor, weights)
    return scores[0] if scores else None
