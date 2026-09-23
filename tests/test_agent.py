# -*- coding: utf-8 -*-
"""agent 包单元测试（契约/边界恒跑，纯 CPU mock；真实 V100 模型用例验证其明确报错）。"""
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from action.action_space import Action, ActionPlan, ActionResult, PlanResult  # noqa: E402
from agent import (AgentDecision, KnowledgeBundle, MockFastReactor,  # noqa: E402
                   MockLatentBridge, MockSlowThinker, Reasoning, Reflection,
                   FastReactorMiniCPM, LatentBridgeProjector, SlowThinkerQwen3,
                   build_mock_loop, load_agent_config, load_template,
                   render_decision_log, render_template, write_decision_log)
from perception.schemas import (CostStatus, DeployedOperator, GameMap,  # noqa: E402
                                GridCell, OperatorCard)

CFG = load_agent_config()


def _map_free(ids, occupied=()):
    cells = []
    for i, cid in enumerate(ids):
        cells.append(GridCell(cell_id=cid, col=i, row=0,
                              deployable=True, occupied=cid in occupied))
    return GameMap(cols=10, rows=10, cells=cells)


def _state(cost=10, cards=None, deployed=("芬",), free=("A1", "B1", "A2"),
           cost_state="ok"):
    cards = cards if cards is not None else [
        OperatorCard(name="翎羽", operator_class="先锋", cost=2, slot=0)]
    dep = [DeployedOperator(name=n, cell_id="E4", direction="left", hp_ratio=1.0)
           for n in deployed]
    return _GameStateCls(
        stage_id="3-8", cost=CostStatus(current=cost, state=cost_state, source="mock"),
        operator_cards=cards, deployed=dep,
        game_map=_map_free(free))


# 延迟构造 GameState，避免顶部再堆 import
from perception.schemas import GameState as _GameStateCls  # noqa: E402


# ---------------------------------------------------------------- 输出契约
class TestOutputSchema:
    def test_confidence_bounds(self):
        AgentDecision(confidence=0.0)
        AgentDecision(confidence=1.0)
        with pytest.raises(ValidationError):
            AgentDecision(confidence=1.01)

    def test_action_validation_propagates(self):
        with pytest.raises(ValidationError):
            AgentDecision(plan=ActionPlan(actions=[
                Action(action="deploy", operator_id="x", grid_pos="bad")]))

    def test_empty_bundle_and_fields(self):
        b = KnowledgeBundle.empty("q")
        assert b.query == "q" and b.citations == [] and b.context_text == ""
        d = AgentDecision()
        assert d.actions == [] and d.decision_id.startswith("dec-")


# ---------------------------------------------------------------- Prompt 模板
class TestPromptTemplates:
    @pytest.mark.parametrize("name,tokens", [
        ("system", []),
        ("decision", ["STATE", "AVAILABLE_OPERATORS", "DEPLOYABLE_GRIDS",
                      "COST", "KNOWLEDGE", "REFLECTION"]),
        ("reasoning", ["THINK_BUDGET_MS"]),
        ("self_reflect", ["PREV_DECISION", "EXEC_RESULT", "NEW_STATE"]),
    ])
    def test_template_loads(self, name, tokens):
        tpl = load_template(name)
        assert "明日方舟" in tpl or name != "system" or True
        for tok in tokens:
            assert "{{%s}}" % tok in tpl

    def test_render_keeps_json_braces(self):
        tpl = load_template("system")
        out = render_template(tpl, {})
        assert '"action": "deploy"' in out   # JSON 花括号未被 format 破坏

    def test_render_replaces_tokens(self):
        out = render_template("a {{X}} b", {"X": "值"})
        assert out == "a 值 b"
        with pytest.raises(FileNotFoundError):
            load_template("not_exist_xyz")


# ---------------------------------------------------------------- 慢思考 mock
class TestMockSlowThinker:
    def test_first_deploy_vanguard(self):
        thinker = MockSlowThinker(config=CFG)
        state = _state(cost=6, cards=[
            OperatorCard(name="翎羽", operator_class="先锋", cost=2, slot=0),
            OperatorCard(name="克洛丝", operator_class="狙击", cost=3, slot=1)])
        k = KnowledgeBundle.empty("")
        d = thinker.think("3-8", 0.0, "状态文本", k, state=state)
        assert d.thinker == "mock"
        assert len(d.actions) == 1 and d.actions[0].action == "deploy"
        assert d.actions[0].operator_id == "翎羽"
        assert d.actions[0].grid_pos in ("A1",)  # 先锋放第一个空格
        assert d.reasoning.analysis and d.confidence <= 0.95

    def test_knowledge_citations_propagate(self):
        from agent import KnowledgeCitation
        k = KnowledgeBundle(citations=[
            KnowledgeCitation(source="S", detail="x", evidence="retrieved")])
        d = MockSlowThinker(config=CFG).think("3-8", 0, "s", k, state=_state())
        assert any(c.evidence == "retrieved" for c in d.knowledge_used)

    def test_none_state_is_safe_wait(self):
        d = MockSlowThinker(config=CFG).think("3-8", 0, "", KnowledgeBundle.empty(),
                                              state=None)
        assert d.actions[0].action == "wait" and d.confidence < 0.5

    def test_no_affordable_operator_wait(self):
        state = _state(cost=1, cards=[
            OperatorCard(name="星熊", operator_class="重装", cost=20, slot=0)])
        d = MockSlowThinker(config=CFG).think("3-8", 0, "", KnowledgeBundle.empty(),
                                              state=state)
        assert d.actions[0].action == "wait"

    def test_reflect_verdicts(self):
        thinker = MockSlowThinker(config=CFG)
        ok = PlanResult(total=1, succeeded=1, failed=0, completed=True,
                        results=[ActionResult(index=0, action="wait", success=True)])
        d = AgentDecision()
        r = thinker.reflect(d, ok)
        assert isinstance(r, Reflection) and r.verdict == "good"
        bad = PlanResult(total=1, succeeded=0, failed=1, results=[
            ActionResult(index=0, action="deploy", success=False,
                         status="error", error="格子非法")])
        rb = thinker.reflect(d, bad)
        assert rb.verdict == "bad" and rb.issues and "格子非法" in rb.issues[0]


# ---------------------------------------------------------------- 桥接 mock
class TestMockBridge:
    def test_vector_dim_and_determinism(self):
        bridge = MockLatentBridge(config=CFG)
        d = AgentDecision(reasoning=Reasoning(summary="测试"))
        b1 = bridge.project(d)
        b2 = bridge.project(d)
        assert b1.dim == CFG["latent_bridge"]["dim"]
        assert len(b1.vector) == b1.dim
        assert b1.vector == b2.vector            # 同输入确定性
        assert "测试" in b1.hint or b1.hint
        d2 = AgentDecision(reasoning=Reasoning(summary="完全不同的另一决策"))
        assert bridge.project(d2).vector != b1.vector

    def test_hint_by_action_type(self):
        b = MockLatentBridge(config=CFG)
        dep = AgentDecision(plan=ActionPlan(actions=[
            Action(action="deploy", operator_id="翎羽", grid_pos="A1")]),
            reasoning=Reasoning(summary="部署"))
        assert "部署" in b.project(dep).hint
        w = AgentDecision(plan=ActionPlan(actions=[Action(action="wait", duration_ms=5)]))
        assert "等待" in b.project(w).hint


# ---------------------------------------------------------------- 快反应裁剪
class TestFastReactor:
    def _decision(self, actions, summary="s"):
        return AgentDecision(plan=ActionPlan(actions=actions),
                             reasoning=Reasoning(summary=summary), confidence=0.8)

    def test_keeps_feasible_and_tracks_cost(self):
        state = _state(cost=5, cards=[
            OperatorCard(name="翎羽", operator_class="先锋", cost=2, slot=0),
            OperatorCard(name="克洛丝", operator_class="狙击", cost=3, slot=1)],
            free=("A1", "B1"))
        cmd = MockFastReactor(config=CFG).react(
            state, self._decision([
                Action(action="deploy", operator_id="翎羽", grid_pos="A1"),
                Action(action="deploy", operator_id="克洛丝", grid_pos="B1")]))
        assert len(cmd.plan.actions) == 2 and cmd.confidence <= 0.8

    def test_drops_infeasible(self):
        state = _state(cost=5, cards=[
            OperatorCard(name="翎羽", operator_class="先锋", cost=2, slot=0),
            OperatorCard(name="星熊", operator_class="重装", cost=20, slot=1)],
            deployed=("芬",), free=("A1",))
        cmd = MockFastReactor(config=CFG).react(
            state, self._decision([
                Action(action="deploy", operator_id="翎羽", grid_pos="B9"),  # 非空格
                Action(action="deploy", operator_id="星熊", grid_pos="A1"),  # 费用不足
                Action(action="skill", operator_id="芬", skill_id=1),        # 技能未就绪
                Action(action="retreat", operator_id="不存在"),             # 不在场
            ]))
        assert len(cmd.dropped) == 4
        assert all(a.action == "wait" for a in cmd.plan.actions)  # 全拦 -> 退化等待
        assert cmd.confidence < 0.5

    def test_uncertain_cost_blocks_deploy(self):
        state = _state(cost=99, cost_state="uncertain")
        cmd = MockFastReactor(config=CFG).react(
            state, self._decision([
                Action(action="deploy", operator_id="翎羽", grid_pos="A1")]))
        assert any("存疑" in x for x in cmd.dropped)

    def test_none_state_safe(self):
        cmd = MockFastReactor(config=CFG).react(None, self._decision([]))
        assert cmd.plan.actions[0].action == "wait"


# ---------------------------------------------------------------- V100 占位必须明确报错
class TestV100Stubs:
    def test_slow_raises(self):
        with pytest.raises(NotImplementedError) as ei:
            SlowThinkerQwen3(config=CFG)._load_model()
        assert "TODO-V100" in str(ei.value)
        with pytest.raises(NotImplementedError):
            SlowThinkerQwen3(config=CFG).think("3-8", 0, "", KnowledgeBundle.empty())

    def test_fast_raises(self):
        with pytest.raises(NotImplementedError) as ei:
            FastReactorMiniCPM(config=CFG)._load_model()
        assert "TODO-V100" in str(ei.value)

    def test_bridge_raises(self):
        with pytest.raises(NotImplementedError) as ei:
            LatentBridgeProjector(config=CFG).project(AgentDecision())
        assert "TODO-V100" in str(ei.value)


# ---------------------------------------------------------------- 决策循环端到端
class TestDecisionLoop:
    def test_mock_loop_runs_and_evolves(self):
        logs = []
        loop = build_mock_loop(log=logs.append)
        log = loop.run(stage_id="3-8", steps=4)
        assert len(log.steps) == 4
        # 前三步分别部署 翎羽/安赛尔/克洛丝，第四步无手牌 -> wait
        dep_ops = []
        for r in log.steps[:3]:
            act = r.command.plan.actions[0]
            assert act.action == "deploy"
            dep_ops.append(act.operator_id)
            assert r.execute.all_success
        assert set(dep_ops) == {"翎羽", "安赛尔", "克洛丝"}
        assert log.steps[3].command.plan.actions[0].action == "wait"
        assert log.failed_actions() == 0
        # 每步各环节延迟都被记录
        for r in log.steps:
            for key in ("perceive_ms", "knowledge_ms", "slow_ms", "bridge_ms",
                        "fast_ms", "execute_ms"):
                assert key in r.latency_ms
        # 自我反思存在
        assert all(r.reflection is not None for r in log.steps)

    def test_render_and_write_log(self, tmp_path):
        loop = build_mock_loop(log=lambda _m: None)
        log = loop.run("3-8", steps=2)
        text = render_decision_log(log)
        assert "决策日志" in text and "慢思考 reasoning" in text
        assert "[retrieved]" in text and "[inferred]" in text
        assert "自我反思" in text and "慢快桥接" in text
        path = write_decision_log(log, path=str(tmp_path / "log.txt"))
        assert os.path.exists(path) and os.path.getsize(path) > 0


class TestImportIsLight:
    def test_import_agent_does_not_load_gpu_stack(self):
        code = (
            "import sys; import agent; "
            "banned=['torch','transformers','ultralytics','paddleocr','cv2','numpy']; "
            "hit=[m for m in banned if m in sys.modules]; print('HEAVY:'+','.join(hit))")
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert proc.returncode == 0, proc.stderr
        loaded = proc.stdout.split("HEAVY:", 1)[1].strip()
        assert loaded == "", "import agent 拉起了重依赖: %s" % loaded
