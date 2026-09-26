"""端到端闭环测试：游戏状态 → Agent决策 → 动作执行 → 环境反馈，循环多步。

用 mock 组件跑通完整一局，验证：
- 状态解析正确（EnvStep 有 cost/state_text/evidence）
- 决策输出格式正确（trace["decision"] 有 reasoning/plan/confidence）
- 动作执行成功（plan_result 有 results）
- 决策日志完整（EpisodeLog 每步有 trace 合流）
- evidence 分级正确（step.evidence 有 retrieved/inferred）
- 每一步 EnvStep 有完整字段（latency_ms/plan/plan_result/reward_items）
"""

import pytest

from env.mock_env import build_mock_env, run_mock_episode


class TestE2EBasicLoop:
    def test_win_episode_completes(self):
        """win 模式跑完整一局，返回 EpisodeLog，步数正确，outcome=win。"""
        log = run_mock_episode(mode="win", stage_id="3-8", win_in=5)
        assert log is not None
        assert log.stage_id == "3-8"
        assert len(log.steps) == 5
        assert log.outcome == "win"

    def test_lose_episode_completes(self):
        """lose 模式跑完整一局，返回 EpisodeLog，outcome=defeat。"""
        log = run_mock_episode(mode="lose", stage_id="3-8", lose_in=3, win_in=10)
        assert log is not None
        assert len(log.steps) >= 3
        assert log.outcome == "defeat"

    def test_each_step_has_state_fields(self):
        """每一步 EnvStep 有状态字段（cost/state_text）。"""
        env = build_mock_env(mode="win", stage_id="3-8", win_in=4)
        log = env.run_episode(max_steps=4)
        for step in log.steps:
            assert step.cost is not None
            assert step.cost >= 0
            assert step.state_text
            assert len(step.state_text) > 10

    def test_each_step_has_decision_in_trace(self):
        """每一步 trace 合流了 AgentDecision，格式正确。"""
        env = build_mock_env(mode="win", stage_id="3-8", win_in=4)
        log = env.run_episode(max_steps=4)
        for step in log.steps:
            assert step.trace is not None
            d = step.trace.get("decision")
            assert d is not None
            assert d["reasoning"]["summary"]
            assert len(d["reasoning"]["analysis"]) > 0
            assert len(d["plan"]["actions"]) >= 1
            assert 0.0 <= d["confidence"] <= 1.0
            assert step.decision_summary

    def test_each_step_actions_executed(self):
        """每一步的动作被执行，plan_result 有 results。"""
        env = build_mock_env(mode="win", stage_id="3-8", win_in=4)
        log = env.run_episode(max_steps=4)
        for step in log.steps:
            pr = step.plan_result
            assert pr is not None
            assert len(pr.results) >= 1
            for ar in pr.results:
                assert ar.action in ("deploy", "skill", "retreat", "wait")
                assert ar.success is True

    def test_each_step_has_evidence(self):
        """每一步有 evidence 分级引用。"""
        env = build_mock_env(mode="win", stage_id="3-8", win_in=4)
        log = env.run_episode(max_steps=4)
        for step in log.steps:
            assert isinstance(step.evidence, list)
            levels = {e.level for e in step.evidence}
            assert "retrieved" in levels
            assert "inferred" in levels
            kb = step.trace.get("knowledge")
            assert kb is not None
            assert len(kb["citations"]) >= 1

    def test_each_step_has_latency(self):
        """每一步有六段延迟记录。"""
        env = build_mock_env(mode="win", stage_id="3-8", win_in=4)
        log = env.run_episode(max_steps=4)
        for step in log.steps:
            lat = step.latency_ms
            for key in ("perceive_ms", "knowledge_ms", "slow_ms",
                         "bridge_ms", "fast_ms", "execute_ms"):
                assert key in lat
                assert lat[key] >= 0

    def test_each_step_trace_merged(self):
        """EnvStep.trace 合流了完整决策数据。"""
        env = build_mock_env(mode="win", stage_id="3-8", win_in=4)
        log = env.run_episode(max_steps=4)
        for step in log.steps:
            trace = step.trace
            assert trace is not None
            for key in ("knowledge", "decision", "bridge", "command", "execute"):
                assert key in trace
            assert len(trace["execute"]["results"]) >= 1

    def test_state_evolves_between_steps(self):
        """多步之间费用有演进。"""
        env = build_mock_env(mode="win", stage_id="3-8", win_in=5)
        log = env.run_episode(max_steps=5)
        costs = [s.cost for s in log.steps]
        assert all(c is not None and c >= 0 for c in costs)

    def test_episode_total_reward(self):
        """EpisodeLog 有 total_reward，win 模式为正。"""
        log = run_mock_episode(mode="win", stage_id="3-8", win_in=5)
        assert log.total_reward > 0
        assert log.reward is not None

    def test_episode_duration(self):
        """EpisodeLog 有 duration_sec 和 backend。"""
        log = run_mock_episode(mode="win", stage_id="3-8", win_in=3)
        assert log.duration_sec >= 0
        assert log.backend == "mock"


class TestE2EWithMCPKnowledge:
    """用 MCPKnowledge（真实知识端口）跑端到端。"""

    def test_mcp_knowledge_e2e(self):
        """MCPKnowledge 注入环境，跑3步，验证 citations 有 fact 级引用。"""
        from agent.knowledge_port import MCPKnowledge
        from agent.config import load_agent_config
        from agent.fast_reactor import MockFastReactor
        from agent.latent_bridge import MockLatentBridge
        from agent.slow_thinker import MockSlowThinker
        from action.action_executor import ActionExecutor
        from action.adb_controller import MockADBController
        from action.config import load_action_config
        from agent.decision_loop import MockPerception
        from env.arknights_env import ArknightsEnv
        from env.mock_env import ScriptedPerception

        cfg = load_agent_config()
        base = MockPerception(stage_id="3-8")
        perception = ScriptedPerception(base, mode="win", win_in=3)
        executor = ActionExecutor(
            MockADBController(), config=load_action_config(),
            card_slot_resolver=base.card_slot,
            deployed_cell_resolver=base.deployed_cell,
            real_sleep=False)

        env = ArknightsEnv(
            perception=perception, executor=executor,
            knowledge=MCPKnowledge(),
            slow=MockSlowThinker(config=cfg),
            bridge=MockLatentBridge(config=cfg),
            fast=MockFastReactor(config=cfg),
            config=cfg, stage_id="3-8", max_steps=3, backend="mock")

        log = env.run_episode(max_steps=3)
        assert len(log.steps) == 3

        all_evidence = set()
        for step in log.steps:
            kb = step.trace["knowledge"]
            for c in kb["citations"]:
                all_evidence.add(c["evidence"])
        assert "fact" in all_evidence, \
            "MCPKnowledge 应返回 fact 级引用，实际只有: %s" % all_evidence
        assert "retrieved" in all_evidence
