# -*- coding: utf-8 -*-
"""
Stage 3 规划层——干员匹配。

输入：可用干员（OperatorTensor）+ 敌人类型 + 路径拦截点
输出：每个拦截点的候选干员（按射程覆盖、费用、克制关系排序）

设计原则：
- 无状态纯函数
- 骨架实现：按职业匹配（近战守路径、远程高台、医疗后排），按费用排序
- 克制关系数据来自知识图谱（COUNTERS边），骨架阶段用占位规则
"""
from typing import Dict, List, Optional, Tuple

from perception.schemas import (
    MAX_OPERATORS,
    OPERATOR_F,
    OperatorTensor,
    StateTensor,
)

# 职业编码（与 perception/state_tensor.py 一致）
_CLASS_ID_TO_NAME = {
    0: "unknown", 1: "先锋", 2: "近卫", 3: "狙击", 4: "术师",
    5: "重装", 6: "医疗", 7: "辅助", 8: "特种", 9: "召唤",
}

# 职业→定位分类
_ROLE_MELEE = {1, 2, 5}    # 先锋/近卫/重装：近战，守地面路径
_ROLE_RANGED = {3, 4, 6, 7}  # 狙击/术师/医疗/辅助：远程，放高台
_ROLE_SUPPORT = {6, 7}      # 医疗/辅助：后排

# 拦截点类型
PointType = str  # "ground_path" | "highland" | "backline"


class OperatorCandidate:
    """单个干员候选，含匹配评分。"""

    def __init__(
        self,
        operator_idx: int,
        name: str,
        operator_class: str,
        cost: float,
        range_id: int,
        score: float,
        match_reason: str,
    ):
        self.operator_idx = operator_idx
        self.name = name
        self.operator_class = operator_class
        self.cost = cost
        self.range_id = range_id
        self.score = score  # 0~1，越高越适合
        self.match_reason = match_reason

    def to_dict(self) -> dict:
        return {
            "operator_idx": self.operator_idx,
            "name": self.name,
            "class": self.operator_class,
            "cost": self.cost,
            "score": round(self.score, 3),
            "reason": self.match_reason,
        }


def _classify_point(
    point: Tuple[int, int],
    map_tensor,
    paths,
) -> PointType:
    """
    分类拦截点类型。

    - "ground_path": 地面路径上的格子（近战位）
    - "highland": 高台格子（远程位）
    - "backline": 后排格子（医疗位）
    """
    c, r = point
    idx = r * 10 * 4 + c * 4
    highland = map_tensor.data[idx + 3] > 0

    if highland:
        return "highland"

    # 检查是否在路径上
    for path in paths:
        if point in path:
            return "ground_path"

    return "backline"


def _score_operator_for_point(
    op_features: List[float],
    point_type: PointType,
    enemy_type_ids: List[int],
) -> Tuple[float, str]:
    """
    为干员在特定拦截点的适配度打分（0~1）。

    评分维度：
    1. 职业-位置匹配（近战守地面、远程放高台、医疗放后排）
    2. 费用效率（费用低加分，但不绝对）
    3. 克制关系（骨架阶段用占位，私服后接知识图谱 COUNTERS）
    """
    class_id = int(op_features[3])
    cost = op_features[0]
    range_id = int(op_features[1])

    score = 0.0
    reasons = []

    # 1. 职业-位置匹配（权重 0.6）
    if point_type == "ground_path":
        if class_id in _ROLE_MELEE:
            score += 0.6
            reasons.append("近战职业守地面路径")
        elif class_id in _ROLE_RANGED:
            score += 0.2
            reasons.append("远程职业也可放地面但非最优")
    elif point_type == "highland":
        if class_id in _ROLE_RANGED:
            score += 0.6
            reasons.append("远程职业放高台")
        elif class_id in _ROLE_MELEE:
            score += 0.1
            reasons.append("近战放高台效果差")
    elif point_type == "backline":
        if class_id in _ROLE_SUPPORT:
            score += 0.6
            reasons.append("医疗/辅助放后排")
        else:
            score += 0.2
            reasons.append("非支援职业放后排")

    # 2. 费用效率（权重 0.2，费用越低分越高）
    if cost > 0:
        cost_score = max(0.0, 1.0 - cost / 20.0)  # 20费以上0分
        score += 0.2 * cost_score
        reasons.append(f"费用{int(cost)}效率{cost_score:.2f}")

    # 3. 克制关系（权重 0.2，骨架阶段占位）
    # TODO-V100: 接入知识图谱 COUNTERS 边，根据敌人类型计算克制加成
    score += 0.1  # 占位：所有干员给基础克制分
    reasons.append("克制关系待接入知识图谱(占位)")

    return min(1.0, score), "; ".join(reasons)


def match_operators(
    state_tensor: StateTensor,
    interception_points: List[Tuple[int, int]],
    paths,
    enemy_type_ids: Optional[List[int]] = None,
    top_k: int = 3,
) -> Dict[Tuple[int, int], List[OperatorCandidate]]:
    """
    为每个拦截点匹配候选干员。

    Args:
        state_tensor: 当前状态张量
        interception_points: 拦截点列表 [(col, row), ...]
        paths: 敌人路径（用于分类拦截点类型）
        enemy_type_ids: 敌人类型ID列表（用于克制匹配，骨架阶段可选）
        top_k: 每个拦截点返回前K个候选

    Returns:
        {拦截点: [候选干员列表（按评分降序）]}
    """
    operator_tensor = state_tensor.operator_tensor
    map_tensor = state_tensor.map_tensor

    if enemy_type_ids is None:
        enemy_type_ids = []

    result = {}

    for point in interception_points:
        point_type = _classify_point(point, map_tensor, paths)
        candidates = []

        for op_idx in range(operator_tensor.valid_count):
            op_features = operator_tensor.operator(op_idx)
            available = op_features[4] > 0
            if not available:
                continue

            class_id = int(op_features[3])
            class_name = _CLASS_ID_TO_NAME.get(class_id, "unknown")
            cost = op_features[0]
            range_id = int(op_features[1])

            score, reason = _score_operator_for_point(
                op_features, point_type, enemy_type_ids
            )

            candidates.append(OperatorCandidate(
                operator_idx=op_idx,
                name=f"operator_{op_idx}",  # 骨架阶段用索引命名，实际应从GameState取名称
                operator_class=class_name,
                cost=cost,
                range_id=range_id,
                score=score,
                match_reason=reason,
            ))

        # 按评分降序，取前K
        candidates.sort(key=lambda c: c.score, reverse=True)
        result[point] = candidates[:top_k]

    return result
