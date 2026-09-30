# -*- coding: utf-8 -*-
"""
Stage 3 规划层——方案生成。

输入：路径分析 + 干员匹配
输出：N个候选方案（每个方案是一组deploy/skill/retreat动作）

设计原则：
- 无状态纯函数
- 骨架实现：贪心选择前N个拦截点，每个点选最优干员
- 完整搜索算法（A*/MCTS/启发式）留到私服到位后再调优
"""
from typing import Dict, List, Optional, Tuple

from perception.schemas import (
    DeployAction,
    Direction,
    StateTensor,
    WaitAction,
)
from planner.operator_matcher import OperatorCandidate


class DeployPlan:
    """一个部署方案：一组部署动作 + 元信息。"""

    def __init__(
        self,
        plan_id: int,
        actions: List[DeployAction],
        total_cost: float,
        coverage: float,
        strategy: str,
    ):
        self.plan_id = plan_id
        self.actions = actions
        self.total_cost = total_cost
        self.coverage = coverage  # 路径覆盖率 0~1
        self.strategy = strategy  # 生成策略描述

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "action_count": len(self.actions),
            "total_cost": self.total_cost,
            "coverage": round(self.coverage, 3),
            "strategy": self.strategy,
            "actions": [a.dict() for a in self.actions],
        }


def _greedy_plan(
    matched: Dict[Tuple[int, int], List[OperatorCandidate]],
    max_deploys: int,
    cost_budget: float,
    coverage_fn,
) -> DeployPlan:
    """
    贪心策略：按拦截点顺序，每个点选评分最高的干员。

    约束：不超过 max_deploys 个部署，总费用不超过 cost_budget。
    """
    actions = []
    total_cost = 0.0
    used_operators = set()
    used_points = set()

    # 按拦截点评分排序（取每个点的最高分）
    sorted_points = sorted(
        matched.keys(),
        key=lambda p: max((c.score for c in matched[p]), default=0),
        reverse=True,
    )

    for point in sorted_points:
        if len(actions) >= max_deploys:
            break
        if point in used_points:
            continue

        candidates = matched.get(point, [])
        for cand in candidates:
            if cand.operator_idx in used_operators:
                continue
            if total_cost + cand.cost > cost_budget:
                continue

            # 选择朝向：远程朝路径方向，近战默认朝上
            direction = "up"  # 骨架阶段默认朝上，私服后根据路径方向计算
            action = DeployAction(
                operator_idx=cand.operator_idx,
                grid_col=point[0],
                grid_row=point[1],
                direction=direction,  # type: ignore
            )
            actions.append(action)
            total_cost += cand.cost
            used_operators.add(cand.operator_idx)
            used_points.add(point)
            break

    coverage = coverage_fn([(a.grid_col, a.grid_row) for a in actions])
    return DeployPlan(
        plan_id=0,
        actions=actions,
        total_cost=total_cost,
        coverage=coverage,
        strategy="greedy: 按拦截点评分降序，每点选最优干员",
    )


def _cost_efficient_plan(
    matched: Dict[Tuple[int, int], List[OperatorCandidate]],
    max_deploys: int,
    cost_budget: float,
    coverage_fn,
) -> DeployPlan:
    """
    费用效率策略：优先选费用低的干员，在预算内部署更多干员。
    """
    actions = []
    total_cost = 0.0
    used_operators = set()

    # 收集所有（点, 候选）对，按费用升序
    all_pairs = []
    for point, cands in matched.items():
        for cand in cands:
            all_pairs.append((point, cand))
    all_pairs.sort(key=lambda x: x[1].cost)

    for point, cand in all_pairs:
        if len(actions) >= max_deploys:
            break
        if cand.operator_idx in used_operators:
            continue
        if total_cost + cand.cost > cost_budget:
            continue

        action = DeployAction(
            operator_idx=cand.operator_idx,
            grid_col=point[0],
            grid_row=point[1],
            direction="up",  # type: ignore
        )
        actions.append(action)
        total_cost += cand.cost
        used_operators.add(cand.operator_idx)

    coverage = coverage_fn([(a.grid_col, a.grid_row) for a in actions])
    return DeployPlan(
        plan_id=1,
        actions=actions,
        total_cost=total_cost,
        coverage=coverage,
        strategy="cost_efficient: 按费用升序，预算内部署更多干员",
    )


def _coverage_max_plan(
    matched: Dict[Tuple[int, int], List[OperatorCandidate]],
    max_deploys: int,
    cost_budget: float,
    coverage_fn,
) -> DeployPlan:
    """
    覆盖率优先策略：选择能覆盖最多路径格子的部署组合。

    骨架实现：贪心选择每次增加覆盖率最多的部署。
    """
    actions = []
    total_cost = 0.0
    used_operators = set()
    current_coverage = 0.0

    for _ in range(max_deploys):
        best_action = None
        best_cost = 0.0
        best_gain = -1.0

        for point, cands in matched.items():
            for cand in cands:
                if cand.operator_idx in used_operators:
                    continue
                if total_cost + cand.cost > cost_budget:
                    continue

                # 计算增加这个部署后的覆盖率增益
                test_points = [(a.grid_col, a.grid_row) for a in actions] + [point]
                new_coverage = coverage_fn(test_points)
                gain = new_coverage - current_coverage

                if gain > best_gain:
                    best_gain = gain
                    best_cost = cand.cost
                    best_action = DeployAction(
                        operator_idx=cand.operator_idx,
                        grid_col=point[0],
                        grid_row=point[1],
                        direction="up",  # type: ignore
                    )

        if best_action is None or best_gain <= 0:
            break

        actions.append(best_action)
        total_cost += best_cost
        used_operators.add(best_action.operator_idx)
        current_coverage += best_gain

    return DeployPlan(
        plan_id=2,
        actions=actions,
        total_cost=total_cost,
        coverage=current_coverage,
        strategy="coverage_max: 贪心选择每次覆盖率增益最大的部署",
    )


def generate_plans(
    state_tensor: StateTensor,
    matched: Dict[Tuple[int, int], List[OperatorCandidate]],
    paths,
    max_plans: int = 3,
    max_deploys: int = 4,
    cost_budget: Optional[float] = None,
) -> List[DeployPlan]:
    """
    生成N个候选部署方案。

    Args:
        state_tensor: 当前状态张量
        matched: 干员匹配结果 {拦截点: [候选干员]}
        paths: 敌人路径（用于覆盖率计算）
        max_plans: 生成方案数量（最多3种策略）
        max_deploys: 每个方案最多部署数
        cost_budget: 费用预算（默认取当前费用的1.5倍）

    Returns:
        候选方案列表（按策略生成，每种策略一个方案）
    """
    from planner.path_analyzer import path_coverage

    if cost_budget is None:
        current_cost = state_tensor.scalars.cost
        cost_budget = current_cost * 1.5 if current_cost > 0 else 20.0

    def coverage_fn(points):
        return path_coverage(points, paths)

    plans = []

    # 策略1：贪心（按评分）
    if max_plans >= 1:
        plans.append(_greedy_plan(matched, max_deploys, cost_budget, coverage_fn))

    # 策略2：费用效率
    if max_plans >= 2:
        plans.append(_cost_efficient_plan(matched, max_deploys, cost_budget, coverage_fn))

    # 策略3：覆盖率优先
    if max_plans >= 3:
        plans.append(_coverage_max_plan(matched, max_deploys, cost_budget, coverage_fn))

    return plans
