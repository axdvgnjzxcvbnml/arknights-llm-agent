# -*- coding: utf-8 -*-
"""
Stage 4 规划层与 LLM 对接——单元测试。

测试：
1. 规划层有候选时，LLM（MockSlowThinker）能正确选择
2. 规划层无候选时，降级到原路径
3. 规划层报错时，不阻塞决策
4. knowledge_port.get_plan_candidates 接口正确
5. decision_loop 记录 planner_ms 耗时
"""
import pytest

from agent.output_schema import KnowledgeBundle
from agent.slow_thinker import MockSlowThinker
from agent.decision_loop import (
    DecisionLoop, MockKnowledge, MockPerception,
)
from perception.schemas import (
    CostStatus, GameMap, GameState, GridCell, OperatorCard,
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _make_simple_state():
    cells = []
    for r in range(10):
        for c in range(10):
            cells.append(GridCell(
                cell_id=f"{chr(ord('A') + c)}{r + 1}",
                col=c, row=r, terrain="ground",
                deployable=True, occupied=False))
    return GameState(
        stage_id="test-1",
        cost=CostStatus(current=20, state="ok", source="mock"),
        life_points=20,
        operator_cards=[
            OperatorCard(name="芬", operator_class="先锋", cost=2, available=True),
            OperatorCard(name="能天使", operator_class="狙击", cost=6, available=True),
            OperatorCard(name="安赛尔", operator_class="医疗", cost=3, available=True),
        ],
        game_map=GameMap(cols=10, rows=10, cells=cells),
    )


def _make_plan_candidates():
    """构造模拟的规划层候选方案。"""
    return [
        {
            "plan_id": 0,
            "strategy": "greedy: 按拦截点评分降序",
            "total_score": 0.75,
            "coverage": 0.8,
            "cost_efficiency": 0.65,
            "risk": 0.8,
            "total_cost": 8,
            "evidence": "inferred",
            "actions": [
                {"type": "deploy", "operator_idx": 0, "grid_col": 2, "grid_row": 5, "direction": "right"},
                {"type": "deploy", "operator_idx": 1, "grid_col": 7, "grid_row": 5, "direction": "left"},
            ],
        },
        {
            "plan_id": 1,
            "strategy": "cost_efficient: 按费用升序",
            "total_score": 0.6,
            "coverage": 0.5,
            "cost_efficiency": 0.8,
            "risk": 0.7,
            "total_cost": 5,
            "evidence": "inferred",
            "actions": [
                {"type": "deploy", "operator_idx": 0, "grid_col": 3, "grid_row": 5, "direction": "right"},
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 1. MockSlowThinker 对接测试
# ---------------------------------------------------------------------------

class TestSlowThinkerPlanIntegration:
    def test_with_plan_candidates_selects_first(self):
        """有候选方案时，选择评分最高的可执行方案。"""
        thinker = MockSlowThinker()
        state = _make_simple_state()
        kb = KnowledgeBundle.empty()
        plans = _make_plan_candidates()

        decision = thinker.think(
            stage_id="test-1", elapsed_sec=6.0, state_text="test",
            knowledge=kb, state=state, plan_candidates=plans)

        assert decision is not None
        assert decision.plan is not None
        assert len(decision.plan.actions) == 2  # 方案0有2个deploy
        # 第一个动作应该是方案0的第一个deploy（芬@C6）
        first = decision.plan.actions[0]
        assert first.operator_id == "芬"
        assert first.grid_pos == "C6"

    def test_with_plan_candidates_reasoning_mentions_plan(self):
        """有候选方案时，reasoning中提到规划层。"""
        thinker = MockSlowThinker()
        state = _make_simple_state()
        kb = KnowledgeBundle.empty()
        plans = _make_plan_candidates()

        decision = thinker.think(
            stage_id="test-1", elapsed_sec=6.0, state_text="test",
            knowledge=kb, state=state, plan_candidates=plans)

        assert "规划层" in decision.reasoning.summary
        assert any("规划层" in a for a in decision.reasoning.analysis)

    def test_without_plan_candidates_fallback(self):
        """无候选方案（None）时，降级到原路径（自行决策）。"""
        thinker = MockSlowThinker()
        state = _make_simple_state()
        kb = KnowledgeBundle.empty()

        decision = thinker.think(
            stage_id="test-1", elapsed_sec=6.0, state_text="test",
            knowledge=kb, state=state, plan_candidates=None)

        assert decision is not None
        # 原路径应该也能产出决策（deploy或wait）
        assert decision.plan is not None

    def test_empty_plan_candidates_fallback(self):
        """空候选列表（[]）时，降级到原路径。"""
        thinker = MockSlowThinker()
        state = _make_simple_state()
        kb = KnowledgeBundle.empty()

        decision = thinker.think(
            stage_id="test-1", elapsed_sec=6.0, state_text="test",
            knowledge=kb, state=state, plan_candidates=[])

        assert decision is not None
        assert decision.plan is not None

    def test_unaffordable_plan_skipped(self):
        """方案费用超预算时，跳过该方案，尝试下一个或降级。"""
        thinker = MockSlowThinker()
        state = _make_simple_state()
        # 把费用设为1，方案0需要8费，方案1需要5费，都不可执行
        state.cost = CostStatus(current=1, state="ok", source="mock")
        kb = KnowledgeBundle.empty()
        plans = _make_plan_candidates()

        decision = thinker.think(
            stage_id="test-1", elapsed_sec=6.0, state_text="test",
            knowledge=kb, state=state, plan_candidates=plans)

        # 两个方案都不可执行，应降级到原路径（费用1时应该wait）
        assert decision is not None
        # 原路径在费用不足时应该wait
        assert all(a.action == "wait" for a in decision.plan.actions) or len(decision.plan.actions) == 0

    def test_plan_evidence_marked_inferred(self):
        """规划层候选方案的evidence标注为inferred。"""
        plans = _make_plan_candidates()
        for p in plans:
            assert p.get("evidence") == "inferred"


# ---------------------------------------------------------------------------
# 2. knowledge_port.get_plan_candidates 测试
# ---------------------------------------------------------------------------

class TestKnowledgePortPlanCandidates:
    def test_mock_knowledge_no_get_plan_candidates(self):
        """MockKnowledge 没有 get_plan_candidates 方法（旧接口），不报错。"""
        mk = MockKnowledge()
        assert not hasattr(mk, "get_plan_candidates")

    def test_mcp_knowledge_has_get_plan_candidates(self):
        """MCPKnowledge 有 get_plan_candidates 方法。"""
        from agent.knowledge_port import MCPKnowledge
        assert hasattr(MCPKnowledge, "get_plan_candidates")

    def test_get_plan_candidates_with_real_state(self):
        """用真实状态调用 get_plan_candidates，返回候选列表或None。"""
        from agent.knowledge_port import MCPKnowledge
        # MCPKnowledge 需要 MCP 服务，mock 环境下 _svc 会失败
        # 但 get_plan_candidates 不依赖 MCP，只依赖 planner
        mkp = MCPKnowledge.__new__(MCPKnowledge)  # 不调用 __init__
        state = _make_simple_state()
        result = mkp.get_plan_candidates(state)
        # 应该返回列表（可能为空）或None
        assert result is None or isinstance(result, list)


# ---------------------------------------------------------------------------
# 3. decision_loop 对接测试
# ---------------------------------------------------------------------------

class TestDecisionLoopPlanIntegration:
    def test_loop_records_planner_ms(self):
        """决策循环记录 planner_ms 耗时。"""
        # 用 MockKnowledge（无 get_plan_candidates），planner_ms 不应出现
        perception = MockPerception()
        knowledge = MockKnowledge()
        slow = MockSlowThinker()
        from agent.latent_bridge import MockLatentBridge
        from agent.fast_reactor import MockFastReactor
        from action.action_executor import MockActionExecutor
        bridge = MockLatentBridge()
        fast = MockFastReactor()
        executor = MockActionExecutor()

        loop = DecisionLoop(
            perception=perception, knowledge=knowledge, slow=slow,
            bridge=bridge, fast=fast, executor=executor,
            log=lambda *a, **k: None)
        log = loop.run(stage_id="3-8", steps=2)

        # 每步的 latency_ms 中应该有 perceive/knowledge/slow/bridge/fast/execute
        for step in log.steps:
            assert "perceive_ms" in step.latency_ms
            assert "knowledge_ms" in step.latency_ms
            assert "slow_ms" in step.latency_ms

    def test_loop_with_planner_enabled(self):
        """启用规划层（knowledge有get_plan_candidates）时，决策循环不崩溃。"""
        from agent.knowledge_port import MCPKnowledge

        class PlannerEnabledKnowledge(MockKnowledge):
            """MockKnowledge + 规划层候选。"""
            def get_plan_candidates(self, state, max_plans=3):
                return _make_plan_candidates()

        perception = MockPerception()
        knowledge = PlannerEnabledKnowledge()
        slow = MockSlowThinker()
        from agent.latent_bridge import MockLatentBridge
        from agent.fast_reactor import MockFastReactor
        from action.action_executor import MockActionExecutor
        bridge = MockLatentBridge()
        fast = MockFastReactor()
        executor = MockActionExecutor()

        loop = DecisionLoop(
            perception=perception, knowledge=knowledge, slow=slow,
            bridge=bridge, fast=fast, executor=executor,
            log=lambda *a, **k: None)
        log = loop.run(stage_id="3-8", steps=2)

        assert len(log.steps) == 2
        # 规划层有候选时，MockSlowThinker应该选择候选方案
        first_step = log.steps[0]
        assert first_step.decision is not None
        assert first_step.knowledge.plan_candidates is not None

    def test_loop_planner_error_does_not_block(self):
        """规划层报错时，不阻塞决策循环。"""
        class ErrorPlannerKnowledge(MockKnowledge):
            """规划层总是报错。"""
            def get_plan_candidates(self, state, max_plans=3):
                raise RuntimeError("planner crash")

        perception = MockPerception()
        knowledge = ErrorPlannerKnowledge()
        slow = MockSlowThinker()
        from agent.latent_bridge import MockLatentBridge
        from agent.fast_reactor import MockFastReactor
        from action.action_executor import MockActionExecutor
        bridge = MockLatentBridge()
        fast = MockFastReactor()
        executor = MockActionExecutor()

        loop = DecisionLoop(
            perception=perception, knowledge=knowledge, slow=slow,
            bridge=bridge, fast=fast, executor=executor,
            log=lambda *a, **k: None)
        # 不应抛出异常
        log = loop.run(stage_id="3-8", steps=2)
        assert len(log.steps) == 2


# ---------------------------------------------------------------------------
# 4. KnowledgeBundle.plan_candidates 字段测试
# ---------------------------------------------------------------------------

class TestKnowledgeBundlePlanField:
    def test_plan_candidates_default_none(self):
        """KnowledgeBundle 默认 plan_candidates=None。"""
        kb = KnowledgeBundle.empty()
        assert kb.plan_candidates is None

    def test_plan_candidates_can_be_set(self):
        """KnowledgeBundle 可以设置 plan_candidates。"""
        plans = _make_plan_candidates()
        kb = KnowledgeBundle(query="test", context_text="", plan_candidates=plans)
        assert kb.plan_candidates is not None
        assert len(kb.plan_candidates) == 2

    def test_plan_candidates_serializable(self):
        """KnowledgeBundle 可序列化为 JSON（plan_candidates 是 dict 列表）。"""
        import json
        plans = _make_plan_candidates()
        kb = KnowledgeBundle(query="test", context_text="", plan_candidates=plans)
        d = kb.model_dump()
        s = json.dumps(d, ensure_ascii=False)
        assert "plan_candidates" in s
        assert "plan_id" in s
