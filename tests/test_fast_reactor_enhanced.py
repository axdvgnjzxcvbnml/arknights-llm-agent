"""快反应引擎增强规则单元测试（MockFastReactor）。

覆盖第二十二批增强：
- 部署优先级排序（先锋/近卫 > 输出 > 医疗/辅助）
- 干员朝向校验（合法/非法）
- 技能时机判断（有敌人/无敌人）
- cost.state == "missing" 保留上一稳定值
- cost.state == "uncertain" 拦截部署但不拦截技能/撤退
- 连续 N 次无决策触发慢思考建议
- 远程干员朝向提示
"""

import pytest

from action.action_space import Action, ActionPlan
from agent.config import load_agent_config
from agent.fast_reactor import MockFastReactor
from agent.output_schema import AgentDecision, Reasoning
from perception.schemas import (
    CostStatus, DeployedOperator, EnemyPresence, GameMap,
    GameState, GridCell, OperatorCard, SkillStatus,
)


def _make_state(cost=15, cost_state="ok", operators=None, deployed=None,
                skills=None, enemies=None, game_map=None):
    """构造测试用 GameState。"""
    if operators is None:
        operators = [
            OperatorCard(name="芬", operator_class="先锋", cost=2, slot=0),
            OperatorCard(name="克洛丝", operator_class="狙击", cost=3, slot=1),
            OperatorCard(name="安赛尔", operator_class="医疗", cost=3, slot=2),
        ]
    if deployed is None:
        deployed = [DeployedOperator(name="芬", cell_id="C3", direction="left")]
    if skills is None:
        skills = [SkillStatus(operator="芬", slot=0, ready=True)]
    if enemies is None:
        enemies = [EnemyPresence(name="冲锋兵", observed_count=3, position_hint="左侧")]
    if game_map is None:
        cells = [GridCell(cell_id="C3", col=2, row=2, terrain="ground",
                           deployable=True, occupied=True),
                 GridCell(cell_id="C4", col=2, row=3, terrain="ground",
                           deployable=True, occupied=False),
                 GridCell(cell_id="D3", col=3, row=2, terrain="ground",
                           deployable=True, occupied=False)]
        game_map = GameMap(cols=10, rows=8, cells=cells)
    return GameState(
        stage_id="3-8",
        cost=CostStatus(current=cost, state=cost_state),
        operator_cards=operators,
        deployed=deployed,
        skills=skills,
        enemies_on_field=enemies,
        game_map=game_map,
    )


def _make_decision(actions, confidence=0.8):
    """构造测试用 AgentDecision。"""
    return AgentDecision(
        decision_id="test-decision-001",
        reasoning=Reasoning(summary="测试决策", analysis=["分析1"]),
        plan=ActionPlan(actions=actions, reason="测试理由"),
        confidence=confidence,
        knowledge_used=[],
    )


def _make_reactor():
    return MockFastReactor(config=load_agent_config())


# ---------------------------------------------------------------- 部署优先级
class TestDeployPriority:
    def test_vanguard_before_medic(self):
        """先锋（阻挡）应排在医疗（辅助）前面。"""
        reactor = _make_reactor()
        state = _make_state(cost=20)
        # 医疗先出现在列表里，但先锋应排到前面
        actions = [
            Action(action="deploy", operator_id="安赛尔", grid_pos="C4", direction="left"),
            Action(action="deploy", operator_id="克洛丝", grid_pos="D3", direction="left"),
        ]
        decision = _make_decision(actions)
        cmd = reactor.react(state, decision)
        deploy_actions = [a for a in cmd.plan.actions if a.action == "deploy"]
        assert len(deploy_actions) == 2
        # 狙击（优先级1）在医疗（优先级2）前面
        assert deploy_actions[0].operator_id == "克洛丝"
        assert deploy_actions[1].operator_id == "安赛尔"

    def test_same_class_sorted_by_name(self):
        """同职业按名字排序（稳定排序）。"""
        reactor = _make_reactor()
        state = _make_state(
            cost=20,
            operators=[
                OperatorCard(name="先锋B", operator_class="先锋", cost=2, slot=0),
                OperatorCard(name="先锋A", operator_class="先锋", cost=2, slot=1),
            ],
            deployed=[],
        )
        actions = [
            Action(action="deploy", operator_id="先锋B", grid_pos="C4", direction="left"),
            Action(action="deploy", operator_id="先锋A", grid_pos="D3", direction="left"),
        ]
        decision = _make_decision(actions)
        cmd = reactor.react(state, decision)
        deploy_actions = [a for a in cmd.plan.actions if a.action == "deploy"]
        assert deploy_actions[0].operator_id == "先锋A"
        assert deploy_actions[1].operator_id == "先锋B"


# ---------------------------------------------------------------- 朝向校验
class TestDirectionValidation:
    def test_pydantic_blocks_invalid_direction(self):
        """非法朝向在 Action 构造时被 Pydantic 拦截（Literal 类型）。"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Action(action="deploy", operator_id="芬", grid_pos="C4", direction="diagonal")

    def test_ranged_direction_confirmation_note(self):
        """远程干员部署时，note 里有朝向确认提示。"""
        reactor = _make_reactor()
        state = _make_state(cost=20, deployed=[])
        actions = [Action(action="deploy", operator_id="克洛丝", grid_pos="C4", direction="left")]
        decision = _make_decision(actions)
        cmd = reactor.react(state, decision)
        assert "朝向" in cmd.note
        assert "克洛丝" in cmd.note


# ---------------------------------------------------------------- 技能时机
class TestSkillTiming:
    def test_skill_with_enemies_passes(self):
        """场上有敌人时，就绪技能可以开。"""
        reactor = _make_reactor()
        state = _make_state(enemies=[EnemyPresence(name="冲锋兵", observed_count=2)])
        actions = [Action(action="skill", operator_id="芬", skill_id=1)]
        decision = _make_decision(actions)
        cmd = reactor.react(state, decision)
        assert any(a.action == "skill" for a in cmd.plan.actions)

    def test_skill_without_enemies_dropped(self):
        """场上无敌人时，技能被拦截（避免空放）。"""
        reactor = _make_reactor()
        state = _make_state(enemies=[])
        actions = [Action(action="skill", operator_id="芬", skill_id=1)]
        decision = _make_decision(actions)
        cmd = reactor.react(state, decision)
        assert not any(a.action == "skill" for a in cmd.plan.actions)
        assert any("无敌人" in d for d in cmd.dropped)


# ---------------------------------------------------------------- cost missing
class TestCostMissing:
    def test_missing_uses_last_stable(self):
        """cost.state == missing 时，使用上一稳定值。"""
        reactor = _make_reactor()
        # 第一帧 ok，费用 15
        state_ok = _make_state(cost=15, cost_state="ok")
        reactor.react(state_ok, _make_decision([Action(action="wait", duration_ms=100)]))
        assert reactor._last_stable_cost == 15
        # 第二帧 missing，应使用 15
        state_missing = _make_state(cost=0, cost_state="missing", deployed=[])
        actions = [Action(action="deploy", operator_id="芬", grid_pos="C4", direction="left")]
        cmd = reactor.react(state_missing, _make_decision(actions))
        # 芬费用 2，上一稳定值 15，应该能部署
        assert any(a.action == "deploy" for a in cmd.plan.actions)
        assert "上一稳定值" in cmd.note

    def test_missing_first_time_uses_zero(self):
        """首次 missing（无上一稳定值）时用 0，部署被拦截。"""
        reactor = _make_reactor()
        state = _make_state(cost=0, cost_state="missing", deployed=[])
        actions = [Action(action="deploy", operator_id="芬", grid_pos="C4", direction="left")]
        cmd = reactor.react(state, decision=_make_decision(actions))
        assert not any(a.action == "deploy" for a in cmd.plan.actions)


# ---------------------------------------------------------------- cost uncertain
class TestCostUncertain:
    def test_uncertain_deploy_dropped(self):
        """cost.state == uncertain 时，部署被拦截。"""
        reactor = _make_reactor()
        state = _make_state(cost=15, cost_state="uncertain", deployed=[])
        actions = [Action(action="deploy", operator_id="芬", grid_pos="C4", direction="left")]
        cmd = reactor.react(state, _make_decision(actions))
        assert not any(a.action == "deploy" for a in cmd.plan.actions)
        assert any("费用读数存疑" in d for d in cmd.dropped)

    def test_uncertain_skill_passes(self):
        """cost.state == uncertain 时，技能不被拦截。"""
        reactor = _make_reactor()
        state = _make_state(cost=15, cost_state="uncertain")
        actions = [Action(action="skill", operator_id="芬", skill_id=1)]
        cmd = reactor.react(state, _make_decision(actions))
        assert any(a.action == "skill" for a in cmd.plan.actions)

    def test_uncertain_retreat_passes(self):
        """cost.state == uncertain 时，撤退不被拦截。"""
        reactor = _make_reactor()
        state = _make_state(cost=15, cost_state="uncertain")
        actions = [Action(action="retreat", operator_id="芬")]
        cmd = reactor.react(state, _make_decision(actions))
        assert any(a.action == "retreat" for a in cmd.plan.actions)


# ---------------------------------------------------------------- 连续无决策
class TestConsecutiveNoop:
    def test_noop_counter_increments(self):
        """全部动作被拦截时，计数器递增。"""
        reactor = _make_reactor()
        state = _make_state(cost=0, deployed=[])  # 费用0，部署必被拦截
        actions = [Action(action="deploy", operator_id="芬", grid_pos="C4", direction="left")]
        reactor.react(state, _make_decision(actions))
        assert reactor._consecutive_noop == 1
        reactor.react(state, _make_decision(actions))
        assert reactor._consecutive_noop == 2

    def test_noop_triggers_slow_hint(self):
        """连续 N 次无决策时，note 里有"建议触发慢思考"。"""
        reactor = _make_reactor()
        reactor._noop_threshold = 2  # 降低阈值便于测试
        state = _make_state(cost=0, deployed=[])
        actions = [Action(action="deploy", operator_id="芬", grid_pos="C4", direction="left")]
        reactor.react(state, _make_decision(actions))  # 第1次
        cmd = reactor.react(state, _make_decision(actions))  # 第2次，达到阈值
        assert "慢思考" in cmd.note
        assert cmd.confidence <= 0.2

    def test_successful_action_resets_counter(self):
        """有动作执行后，计数器归零。"""
        reactor = _make_reactor()
        state_fail = _make_state(cost=0, deployed=[])
        actions_fail = [Action(action="deploy", operator_id="芬", grid_pos="C4", direction="left")]
        reactor.react(state_fail, _make_decision(actions_fail))
        assert reactor._consecutive_noop == 1
        # 成功执行一个 wait
        state_ok = _make_state(cost=15)
        reactor.react(state_ok, _make_decision([Action(action="wait", duration_ms=100)]))
        assert reactor._consecutive_noop == 0


# ---------------------------------------------------------------- 综合
class TestFastReactorEnhanced:
    def test_mixed_actions_priority_and_filter(self):
        """混合动作：部署按优先级排序，不可执行的被拦截。"""
        reactor = _make_reactor()
        state = _make_state(cost=20, deployed=[])
        actions = [
            Action(action="deploy", operator_id="安赛尔", grid_pos="C4", direction="left"),
            Action(action="deploy", operator_id="芬", grid_pos="D3", direction="left"),
            Action(action="deploy", operator_id="不存在", grid_pos="C4", direction="left"),
        ]
        cmd = reactor.react(state, _make_decision(actions))
        deploy_actions = [a for a in cmd.plan.actions if a.action == "deploy"]
        # 2个成功部署（芬、安赛尔），1个被拦截（不存在）
        assert len(deploy_actions) == 2
        # 先锋（芬）在医疗（安赛尔）前面
        assert deploy_actions[0].operator_id == "芬"
        assert deploy_actions[1].operator_id == "安赛尔"
        assert len(cmd.dropped) == 1

    def test_confidence_lowered_on_uncertain(self):
        """cost uncertain 时置信度下调。"""
        reactor = _make_reactor()
        state = _make_state(cost=15, cost_state="uncertain")
        actions = [Action(action="skill", operator_id="芬", skill_id=1)]
        cmd = reactor.react(state, _make_decision(actions, confidence=0.9))
        assert cmd.confidence <= 0.5
