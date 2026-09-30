# -*- coding: utf-8 -*-
"""
Stage 3 规划层——单元测试。

测试：
1. 路径分析：给定简单地图+敌人，验证路径正确
2. 干员匹配：给定干员+敌人，验证候选排序合理
3. 方案生成：验证至少生成1个合法方案
4. 方案评分：验证评分在0-1之间
"""
import pytest

from perception.schemas import (
    MAP_H,
    MAP_W,
    CostStatus,
    DeployedOperator,
    EnemyPresence,
    GameMap,
    GameState,
    GridCell,
    OperatorCard,
    StateTensor,
)
from perception.state_tensor import state_to_tensor
from planner.path_analyzer import (
    analyze_paths,
    bfs_path,
    path_coverage,
    _walkable_cells,
)
from planner.operator_matcher import match_operators, _CLASS_ID_TO_NAME
from planner.plan_generator import generate_plans, DeployPlan
from planner.plan_scorer import score_all_plans, best_plan, PlanScore


# ---------------------------------------------------------------------------
# Fixture：构造测试用 StateTensor
# ---------------------------------------------------------------------------

def _make_simple_map():
    """构造简单地图：全部地面，全部可部署。"""
    cells = []
    for r in range(MAP_H):
        for c in range(MAP_W):
            cell_id = f"{chr(ord('A') + c)}{r + 1}"
            cells.append(GridCell(
                cell_id=cell_id, col=c, row=r,
                terrain="ground", deployable=True, occupied=False,
            ))
    return GameMap(cols=MAP_W, rows=MAP_H, cells=cells)


def _make_test_state():
    """构造测试用 GameState → StateTensor。"""
    game_map = _make_simple_map()
    state = GameState(
        stage_id="test-1",
        cost=CostStatus(current=15, state="ok", source="mock"),
        life_points=20,
        deploy_limit=8,
        operator_cards=[
            OperatorCard(name="芬", operator_class="先锋", cost=2, available=True),
            OperatorCard(name="能天使", operator_class="狙击", cost=6, available=True),
            OperatorCard(name="安赛尔", operator_class="医疗", cost=3, available=True),
            OperatorCard(name="星熊", operator_class="重装", cost=16, available=True),
        ],
        enemies_on_field=[
            EnemyPresence(name="源石虫", observed_count=3, position_hint="左侧"),
        ],
        game_map=game_map,
        timing_source="estimated",
    )
    return state_to_tensor(state)


# ---------------------------------------------------------------------------
# 1. 路径分析测试
# ---------------------------------------------------------------------------

class TestPathAnalyzer:
    def test_bfs_simple_path(self):
        """BFS 简单路径：起点到终点的直线路径。"""
        walkable = {(c, r) for c in range(5) for r in range(5)}
        path = bfs_path((0, 0), (4, 0), walkable)
        assert path is not None
        assert path[0] == (0, 0)
        assert path[-1] == (4, 0)
        assert len(path) == 5  # 直线5格

    def test_bfs_no_path(self):
        """BFS 不可达：返回 None。"""
        walkable = {(0, 0), (1, 0)}  # 只有两个格子
        path = bfs_path((0, 0), (4, 4), walkable)
        assert path is None

    def test_bfs_same_point(self):
        """BFS 起点=终点：返回单元素路径。"""
        walkable = {(0, 0)}
        path = bfs_path((0, 0), (0, 0), walkable)
        assert path == [(0, 0)]

    def test_walkable_cells(self):
        """可行走格子提取：地面格子可行走。"""
        state_tensor = _make_test_state()
        walkable = _walkable_cells(state_tensor.map_tensor)
        assert len(walkable) == MAP_H * MAP_W  # 全部地面

    def test_analyze_paths_basic(self):
        """路径分析基本功能：返回路径和拦截点。"""
        state_tensor = _make_test_state()
        result = analyze_paths(state_tensor)
        assert "paths" in result
        assert "interception_points" in result
        assert "path_lengths" in result
        assert len(result["paths"]) > 0
        assert len(result["interception_points"]) > 0

    def test_path_coverage(self):
        """路径覆盖率计算。"""
        paths = [[(0, 0), (1, 0), (2, 0), (3, 0)]]
        # 拦截点在路径旁边（曼哈顿距离<=1）
        coverage = path_coverage([(1, 1)], paths)
        assert 0 < coverage <= 1.0
        # 拦截点远离路径
        coverage_zero = path_coverage([(9, 9)], paths)
        assert coverage_zero == 0.0


# ---------------------------------------------------------------------------
# 2. 干员匹配测试
# ---------------------------------------------------------------------------

class TestOperatorMatcher:
    def test_match_returns_candidates(self):
        """干员匹配：每个拦截点返回候选列表。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:3]  # 取前3个拦截点
        matched = match_operators(state_tensor, points, path_result["paths"])
        assert len(matched) == len(points)
        for point, cands in matched.items():
            assert len(cands) > 0
            for cand in cands:
                assert 0.0 <= cand.score <= 1.0

    def test_match_sorting(self):
        """干员匹配：候选按评分降序排列。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:1]
        matched = match_operators(state_tensor, points, path_result["paths"], top_k=4)
        cands = list(matched.values())[0]
        scores = [c.score for c in cands]
        assert scores == sorted(scores, reverse=True)

    def test_match_available_only(self):
        """干员匹配：只匹配可用干员。"""
        # 构造一个所有干员不可用的状态
        game_map = _make_simple_map()
        state = GameState(
            cost=CostStatus(current=15, state="ok", source="mock"),
            operator_cards=[
                OperatorCard(name="x", operator_class="先锋", cost=2, available=False),
            ],
            game_map=game_map,
        )
        state_tensor = state_to_tensor(state)
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:1]
        matched = match_operators(state_tensor, points, path_result["paths"])
        # 不可用干员不应出现在候选中
        for cands in matched.values():
            assert len(cands) == 0

    def test_match_class_names(self):
        """干员匹配：职业名称映射正确。"""
        assert _CLASS_ID_TO_NAME[1] == "先锋"
        assert _CLASS_ID_TO_NAME[3] == "狙击"
        assert _CLASS_ID_TO_NAME[6] == "医疗"
        assert _CLASS_ID_TO_NAME[0] == "unknown"


# ---------------------------------------------------------------------------
# 3. 方案生成测试
# ---------------------------------------------------------------------------

class TestPlanGenerator:
    def test_generate_at_least_one_plan(self):
        """方案生成：至少生成1个合法方案。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        plans = generate_plans(state_tensor, matched, path_result["paths"], max_plans=3)
        assert len(plans) >= 1
        for plan in plans:
            assert isinstance(plan, DeployPlan)
            assert len(plan.actions) >= 0

    def test_plan_actions_legal(self):
        """方案生成：动作参数合法。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        plans = generate_plans(state_tensor, matched, path_result["paths"], max_plans=1)
        plan = plans[0]
        for action in plan.actions:
            assert 0 <= action.operator_idx < 12
            assert 0 <= action.grid_col < MAP_W
            assert 0 <= action.grid_row < MAP_H
            assert action.direction in ("up", "down", "left", "right")

    def test_plan_cost_within_budget(self):
        """方案生成：总费用不超过预算。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        budget = 10.0
        plans = generate_plans(
            state_tensor, matched, path_result["paths"],
            max_plans=3, cost_budget=budget,
        )
        for plan in plans:
            assert plan.total_cost <= budget + 0.01  # 浮点容差

    def test_plan_strategies_different(self):
        """方案生成：不同策略生成的方案可能不同。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        plans = generate_plans(state_tensor, matched, path_result["paths"], max_plans=3)
        # 至少有两种不同的策略描述
        strategies = {p.strategy for p in plans}
        assert len(strategies) >= 2

    def test_empty_match_no_crash(self):
        """方案生成：空匹配不崩溃。"""
        state_tensor = _make_test_state()
        plans = generate_plans(state_tensor, {}, [], max_plans=3)
        assert len(plans) == 3  # 3种策略都生成（可能是空方案）
        for plan in plans:
            assert len(plan.actions) == 0


# ---------------------------------------------------------------------------
# 4. 方案评分测试
# ---------------------------------------------------------------------------

class TestPlanScorer:
    def test_score_in_range(self):
        """方案评分：综合评分在0-1之间。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        plans = generate_plans(state_tensor, matched, path_result["paths"], max_plans=3)
        scores = score_all_plans(plans, state_tensor)
        assert len(scores) == len(plans)
        for score in scores:
            assert isinstance(score, PlanScore)
            assert 0.0 <= score.total_score <= 1.0
            assert 0.0 <= score.coverage_score <= 1.0
            assert 0.0 <= score.cost_efficiency <= 1.0
            assert 0.0 <= score.risk_score <= 1.0

    def test_scores_sorted(self):
        """方案评分：按综合评分降序排列。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        plans = generate_plans(state_tensor, matched, path_result["paths"], max_plans=3)
        scores = score_all_plans(plans, state_tensor)
        totals = [s.total_score for s in scores]
        assert totals == sorted(totals, reverse=True)

    def test_best_plan_returns_highest(self):
        """方案评分：best_plan返回评分最高的。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        plans = generate_plans(state_tensor, matched, path_result["paths"], max_plans=3)
        best = best_plan(plans, state_tensor)
        assert best is not None
        all_scores = score_all_plans(plans, state_tensor)
        assert best.total_score == all_scores[0].total_score

    def test_empty_plans_no_crash(self):
        """方案评分：空方案列表不崩溃。"""
        state_tensor = _make_test_state()
        scores = score_all_plans([], state_tensor)
        assert len(scores) == 0
        best = best_plan([], state_tensor)
        assert best is None

    def test_custom_weights(self):
        """方案评分：自定义权重生效。"""
        state_tensor = _make_test_state()
        path_result = analyze_paths(state_tensor)
        points = path_result["interception_points"][:5]
        matched = match_operators(state_tensor, points, path_result["paths"])
        plans = generate_plans(state_tensor, matched, path_result["paths"], max_plans=1)
        # 覆盖率权重1.0，其他0
        scores_cov = score_all_plans(plans, state_tensor, weights={"coverage": 1.0, "cost": 0.0, "risk": 0.0})
        # 费用权重1.0，其他0
        scores_cost = score_all_plans(plans, state_tensor, weights={"coverage": 0.0, "cost": 1.0, "risk": 0.0})
        # 两种权重下的评分可能不同
        assert scores_cov[0].total_score != scores_cost[0].total_score or scores_cov[0].coverage_score == scores_cov[0].cost_efficiency
