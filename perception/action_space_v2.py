# -*- coding: utf-8 -*-
"""
Stage 2 形式化动作空间（可枚举）。

从 GameState + StateTensor 生成当前状态下所有合法动作的枚举列表。
搜索层可以直接遍历这个空间，评估每个动作的价值。

动作类型：
- deploy(operator_idx, grid_col, grid_row, direction)：部署干员
- skill(deployed_idx)：开启技能
- retreat(deployed_idx)：撤退干员
- wait()：等待（不操作）

合法性约束：
- deploy：干员可用（费用够）、格子可部署且未占用、干员未部署
- skill：已部署干员存在、技能可用（冷却好）
- retreat：已部署干员存在
- wait：恒合法

纯 CPU，不依赖 GPU/模拟器。
"""
from typing import List, Optional

from perception.schemas import (
    MAX_DEPLOYED,
    MAX_OPERATORS,
    MAP_H,
    MAP_W,
    ActionSpaceV2,
    DeployAction,
    DeployedOperator,
    Direction,
    GameState,
    RetreatAction,
    SkillAction,
    WaitAction,
)
from perception.state_tensor import StateTensor, state_to_tensor


def _deployable_cells(state: GameState) -> List[tuple]:
    """返回所有可部署格子的 (col, row) 列表。"""
    if state.game_map is None:
        return []
    cells = []
    for cell in state.game_map.cells:
        if cell.deployable and not cell.occupied:
            if 0 <= cell.col < MAP_W and 0 <= cell.row < MAP_H:
                cells.append((cell.col, cell.row))
    return cells


def _available_operators(state: GameState) -> List[int]:
    """返回可用干员的索引列表（费用够且在轮换中）。"""
    indices = []
    for i, card in enumerate(state.operator_cards):
        if i >= MAX_OPERATORS:
            break
        if card.available:
            indices.append(i)
    return indices


def _deployed_names(state: GameState) -> set:
    """返回已部署干员名称集合（避免重复部署）。"""
    return {dep.name for dep in state.deployed}


def build_action_space(
    state: GameState,
    tensor: Optional[StateTensor] = None,
    include_deploy: bool = True,
    include_skill: bool = True,
    include_retreat: bool = True,
) -> ActionSpaceV2:
    """
    从 GameState 生成当前状态下所有合法动作的枚举。

    Args:
        state: 当前游戏状态
        tensor: 预计算的张量（可选，不传则自动计算）
        include_deploy: 是否包含部署动作
        include_skill: 是否包含技能动作
        include_retreat: 是否包含撤退动作

    Returns:
        ActionSpaceV2: 可枚举的动作空间

    动作在列表中的顺序：deploy → skill → retreat → wait
    """
    if tensor is None:
        tensor = state_to_tensor(state)

    actions: List = []
    deploy_count = 0
    skill_count = 0
    retreat_count = 0

    deployed_names = _deployed_names(state)
    deployable_cells = _deployable_cells(state)

    # --- 部署动作 ---
    if include_deploy:
        for op_idx in _available_operators(state):
            card = state.operator_cards[op_idx]
            # 已部署的干员不能再部署
            if card.name in deployed_names:
                continue
            for col, row in deployable_cells:
                # 每个格子4个朝向
                for direction in ("up", "down", "left", "right"):
                    actions.append(DeployAction(
                        operator_idx=op_idx,
                        grid_col=col,
                        grid_row=row,
                        direction=direction,  # type: ignore
                    ))
                    deploy_count += 1

    # --- 技能动作 ---
    if include_skill:
        for dep_idx, dep in enumerate(state.deployed):
            if dep_idx >= MAX_DEPLOYED:
                break
            # 简化：所有已部署干员都可以开技能（实际应检查冷却，第一版不做精细判断）
            actions.append(SkillAction(deployed_idx=dep_idx))
            skill_count += 1

    # --- 撤退动作 ---
    if include_retreat:
        for dep_idx, dep in enumerate(state.deployed):
            if dep_idx >= MAX_DEPLOYED:
                break
            actions.append(RetreatAction(deployed_idx=dep_idx))
            retreat_count += 1

    # --- 等待动作（恒有） ---
    actions.append(WaitAction())

    return ActionSpaceV2(
        actions=actions,
        deploy_count=deploy_count,
        skill_count=skill_count,
        retreat_count=retreat_count,
        wait_count=1,
    )


def action_to_dict(action) -> dict:
    """将动作转为可序列化的字典（便于日志/JSON输出）。"""
    d = action.dict()
    return d


def action_description(action) -> str:
    """生成动作的人类可读描述（便于日志/调试）。"""
    if isinstance(action, DeployAction):
        return f"deploy(op[{action.operator_idx}] @ ({action.grid_col},{action.grid_row}) {action.direction})"
    elif isinstance(action, SkillAction):
        return f"skill(deployed[{action.deployed_idx}])"
    elif isinstance(action, RetreatAction):
        return f"retreat(deployed[{action.deployed_idx}])"
    elif isinstance(action, WaitAction):
        return "wait()"
    return "unknown"


def estimate_space_size(state: GameState) -> dict:
    """
    估算动作空间大小（不实际生成，用于评估搜索复杂度）。

    返回各类型动作的预估数量和总数。
    """
    n_available = len(_available_operators(state))
    n_deployable = len(_deployable_cells(state))
    n_deployed = min(len(state.deployed), MAX_DEPLOYED)
    deployed_names = _deployed_names(state)

    # 扣除已部署的干员
    n_deployable_ops = sum(
        1 for c in state.operator_cards[:MAX_OPERATORS]
        if c.available and c.name not in deployed_names
    )

    deploy_est = n_deployable_ops * n_deployable * 4  # 4个朝向
    skill_est = n_deployed
    retreat_est = n_deployed
    wait_est = 1

    return {
        "deploy": deploy_est,
        "skill": skill_est,
        "retreat": retreat_est,
        "wait": wait_est,
        "total": deploy_est + skill_est + retreat_est + wait_est,
        "available_operators": n_available,
        "deployable_cells": n_deployable,
        "deployed": n_deployed,
    }
