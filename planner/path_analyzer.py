# -*- coding: utf-8 -*-
"""
Stage 3 规划层——敌人路径分析。

输入：StateTensor 的地图张量 + 敌人张量
输出：每条敌人路径的走向、关键拦截点

设计原则：
- 无状态纯函数：输入状态输出路径，不持有内部状态
- 骨架实现：BFS 从敌人位置到地图出口，标记路径格子
- 搜索算法（A*/MCTS）留到私服到位后再调优
"""
from typing import Dict, List, Optional, Set, Tuple

from perception.schemas import (
    MAP_H,
    MAP_W,
    EnemyTensor,
    MapTensor,
    StateTensor,
)

# 格子坐标 (col, row)
Cell = Tuple[int, int]

# 4 方向移动
_DIRECTIONS = [(0, 1), (0, -1), (1, 0), (-1, 0)]


def _walkable_cells(map_tensor: MapTensor) -> Set[Cell]:
    """
    从地图张量提取可行走格子（敌人可以通过的格子）。

    简化假设：除了"不可部署且非高台"的格子（障碍物），其他都可行走。
    实际明日方舟中敌人走固定路径，私服到位后应用真实路径数据。
    """
    walkable = set()
    for r in range(MAP_H):
        for c in range(MAP_W):
            idx = r * MAP_W * 4 + c * 4
            deployable = map_tensor.data[idx + 0]
            occupied = map_tensor.data[idx + 1]
            ground = map_tensor.data[idx + 2]
            highland = map_tensor.data[idx + 3]
            # 敌人走地面格子（高台敌人不走），不被已占用阻挡（敌人可以穿过干员？实际不能，但简化处理）
            if ground > 0 and occupied == 0:
                walkable.add((c, r))
    return walkable


def bfs_path(
    start: Cell,
    goal: Cell,
    walkable: Set[Cell],
) -> Optional[List[Cell]]:
    """
    BFS 求从 start 到 goal 的最短路径。

    返回路径格子列表（含起点和终点），不可达返回 None。
    """
    if start not in walkable or goal not in walkable:
        return None
    if start == goal:
        return [start]

    from collections import deque
    queue = deque([start])
    visited = {start: None}  # cell -> parent

    while queue:
        current = queue.popleft()
        if current == goal:
            # 回溯路径
            path = []
            node = current
            while node is not None:
                path.append(node)
                node = visited[node]
            return list(reversed(path))

        for dc, dr in _DIRECTIONS:
            nxt = (current[0] + dc, current[1] + dr)
            if nxt in walkable and nxt not in visited:
                visited[nxt] = current
                queue.append(nxt)

    return None


def analyze_paths(
    state_tensor: StateTensor,
    entry_points: Optional[List[Cell]] = None,
    exit_points: Optional[List[Cell]] = None,
) -> Dict[str, object]:
    """
    分析敌人路径，输出路径走向和关键拦截点。

    Args:
        state_tensor: 当前状态张量
        entry_points: 敌人入口格子列表（默认左侧中间）
        exit_points: 蓝门/出口格子列表（默认右侧中间）

    Returns:
        {
            "paths": List[List[Cell]] — 每条路径的格子序列
            "interception_points": List[Cell] — 关键拦截点（路径上的可部署格子）
            "path_lengths": List[int] — 每条路径长度
            "entry_points": List[Cell] — 使用的入口
            "exit_points": List[Cell] — 使用的出口
        }
    """
    map_tensor = state_tensor.map_tensor
    enemy_tensor = state_tensor.enemy_tensor
    walkable = _walkable_cells(map_tensor)

    # 默认入口：左侧（col=0）中间行
    if entry_points is None:
        entry_points = [(0, MAP_H // 2)]
    # 默认出口：右侧（col=MAP_W-1）中间行
    if exit_points is None:
        exit_points = [(MAP_W - 1, MAP_H // 2)]

    paths = []
    all_path_cells: Set[Cell] = set()

    for entry in entry_points:
        for exit_pt in exit_points:
            path = bfs_path(entry, exit_pt, walkable)
            if path:
                paths.append(path)
                all_path_cells.update(path)

    # 关键拦截点：路径上的可部署格子（敌人经过时可以被攻击的位置）
    interception_points = []
    for cell in sorted(all_path_cells):
        c, r = cell
        idx = r * MAP_W * 4 + c * 4
        deployable = map_tensor.data[idx + 0]
        if deployable > 0:
            interception_points.append(cell)

    return {
        "paths": paths,
        "interception_points": interception_points,
        "path_lengths": [len(p) for p in paths],
        "entry_points": entry_points,
        "exit_points": exit_points,
        "enemy_count": enemy_tensor.valid_count,
    }


def path_coverage(
    interception_points: List[Cell],
    paths: List[List[Cell]],
) -> float:
    """
    计算拦截点对路径的覆盖率。

    简化：拦截点相邻格子（曼哈顿距离<=1）视为覆盖路径格子。
    返回 0.0~1.0。
    """
    if not paths:
        return 0.0

    covered: Set[Cell] = set()
    for ip in interception_points:
        for path in paths:
            for cell in path:
                if abs(ip[0] - cell[0]) + abs(ip[1] - cell[1]) <= 1:
                    covered.add(cell)

    total_path_cells = set()
    for path in paths:
        total_path_cells.update(path)

    if not total_path_cells:
        return 0.0

    return len(covered) / len(total_path_cells)
