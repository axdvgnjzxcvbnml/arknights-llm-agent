# -*- coding: utf-8 -*-
"""env 包单元测试：奖励评估、Gym 风格接口、mock 对局（纯 CPU，恒跑）。"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from action.action_space import Action, ActionPlan  # noqa: E402
from agent.output_schema import FastCommand  # noqa: E402
from env import (ArknightsEnv, EpisodeReward, RewardConfig,  # noqa: E402
                 build_mock_env, coerce_plan, render_episode_report)


# ---------------------------------------------------------------- 轻量假状态
class _Cost(object):
    def __init__(self, current, limit=99):
        self.current = current
        self.limit = limit


class _S(object):
    def __init__(self, life, cost_current=10, cost_limit=99):
        self.life_points = life
        self.cost = _Cost(cost_current, cost_limit)


# ---------------------------------------------------------------- 奖励
class TestReward:
    def test_win_bonus(self):
        r = EpisodeReward().reset(initial_life=3)
        r.observe(_S(3), dt_sec=1.0)
        b = r.finalize("win")
        assert b.win_bonus == 100 and b.total == 100 and b.leaked == 0

    def test_leak_penalty_per_life_point(self):
        r = EpisodeReward().reset(initial_life=3)
        r.observe(_S(2), dt_sec=1.0)
        r.observe(_S(0), dt_sec=1.0)
        b = r.finalize("defeat")
        assert b.leaked == 3 and b.leak_penalty == -30 and b.total == -30
        assert b.life_start == 3 and b.life_end == 0
        assert any(i.name == "leak" for i in b.items)

    def test_overcost_per_second(self):
        r = EpisodeReward().reset(initial_life=3)
        r.observe(_S(3, cost_current=99, cost_limit=99), dt_sec=2.0)
        r.observe(_S(3, cost_current=50, cost_limit=99), dt_sec=1.0)
        b = r.finalize("aborted")
        assert b.overcost_sec == 2.0 and b.overcost_penalty == -2.0
        assert b.total == -2.0

    def test_partial_second_overcost(self):
        r = EpisodeReward().reset(initial_life=3)
        items = r.observe(_S(3, 99, 99), dt_sec=0.5)
        assert items and abs(items[0].delta + 0.5) < 1e-6

    def test_no_overcost_when_below_limit(self):
        r = EpisodeReward().reset(initial_life=3)
        assert r.observe(_S(3, 98, 99), dt_sec=5.0) == []

    def test_custom_config(self):
        r = EpisodeReward(RewardConfig(win_bonus=50, leak_penalty=20,
                                       overcost_per_sec=3))
        r.reset(3)
        r.observe(_S(2), 1.0)
        b = r.finalize("win")
        assert b.win_bonus == 50 and b.leak_penalty == -20 and b.total == 30


# ---------------------------------------------------------------- 动作归一化
class TestCoercePlan:
    def test_variants(self):
        a = Action(action="wait", duration_ms=10)
        assert coerce_plan(a).actions[0].action == "wait"
        lst = coerce_plan([a])
        assert isinstance(lst, ActionPlan) and len(lst.actions) == 1
        plan = ActionPlan(actions=[a])
        assert coerce_plan(plan) is plan
        cmd = FastCommand(plan=plan)
        assert coerce_plan(cmd).actions[0].action == "wait"
        with pytest.raises(TypeError):
            coerce_plan(123)


# ---------------------------------------------------------------- Gym 接口 / mock 对局
class TestMockEpisodes:
    def test_win_episode(self):
        env = build_mock_env(mode="win", win_in=10)
        log = env.run_episode("3-8")
        assert log.outcome == "win"
        assert len(log.steps) == 10
        assert env.is_done() and env.get_state() is not None
        assert log.reward.total == 100
        # 每步都有状态文本、执行结果、动作
        for st in log.steps:
            assert st.state_text and st.plan_result is not None
            assert st.plan_result.total >= 1

    def test_lose_episode(self):
        env = build_mock_env(mode="lose", lose_in=3)
        log = env.run_episode("3-8")
        assert log.outcome == "defeat"
        assert len(log.steps) == 3
        assert log.steps[-1].life == 0
        assert log.reward.leaked == 3 and log.reward.total == -30

    def test_timeout_episode(self):
        env = build_mock_env(mode="win", win_in=100)
        env.max_steps = 2
        log = env.run_episode("3-8", max_steps=2)
        assert log.outcome == "timeout"
        assert len(log.steps) == 2

    def test_external_gym_drive(self):
        # 不使用内置 policy，外部手动 reset/step
        env = build_mock_env(mode="win", win_in=2)
        with pytest.raises(RuntimeError):
            env.step(Action(action="wait", duration_ms=10))   # 未 reset
        state0 = env.reset("3-8")
        assert state0 is not None and state0.life_points == 3
        s1, r1, done1, info = env.step(Action(action="wait", duration_ms=10))
        assert done1 is False and isinstance(r1, (int, float)) and "tick" in info
        s2, r2, done2, _ = env.step(Action(action="wait", duration_ms=10))
        assert done2 is True and env.outcome == "win"
        log = env.get_log()
        assert log.reward.total == 100 and len(log.steps) == 2

    def test_close_aborted(self):
        env = build_mock_env(mode="win", win_in=10)
        env.reset()
        env.step(Action(action="wait", duration_ms=10))
        log = env.close("aborted")
        assert log.outcome == "aborted" and env.is_done()

    def test_episode_report_content(self):
        log = build_mock_env(mode="win", win_in=3).run_episode("3-8")
        text = render_episode_report(log)
        assert "对局报告" in text
        assert "通关" in text and "奖励明细" in text and "决策" in text
        assert "耐久" in text and "耗时" in text


class TestImportIsLight:
    def test_import_env_no_gpu_stack(self):
        code = (
            "import sys; import env; "
            "banned=['torch','transformers','ultralytics','paddleocr','numpy']; "
            "hit=[m for m in banned if m in sys.modules]; print('HEAVY:'+','.join(hit))")
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.split("HEAVY:", 1)[1].strip() == ""
