# Mock 环境：用全套 mock 组件模拟完整一局，CPU 侧从 reset 跑到 is_done。
# 真实模拟器在 V100/真机阶段替换注入的 perception/executor，ArknightsEnv 接口不变。
# 注意：agent/perception/action 均在工厂函数内延迟导入，保证 `import env` 不拉起 numpy/torch。
"""Mock 对局环境。

两个脚本化结局：
- mode="win"（默认）：第 win_in 步（默认 10）关卡被清空 -> 通关；
- mode="lose"：第 lose_in 步（默认 3）目标耐久归零 -> 失败。

战局演进（费用回复、部署离手牌/占格）复用 agent.decision_loop.MockPerception；
本模块只额外用 ScriptedPerception 控制"通关/生命归零"两个终局信号。
"""

from typing import Optional

from .arknights_env import ArknightsEnv

__all__ = ["ScriptedPerception", "build_mock_env", "run_mock_episode"]


class ScriptedPerception(object):
    """包装一个基础 mock 感知，叠加脚本化的终局（通关 / 生命归零）。"""

    def __init__(self, base, mode="win", win_in=10, lose_in=3):
        assert mode in ("win", "lose")
        self.base = base
        self.mode = mode
        self.win_in = int(win_in)
        self.lose_in = int(lose_in)
        self._n = 0   # perceive 调用计数（reset 的首次感知也算 1）

    def perceive(self, elapsed_sec):
        pf = self.base.perceive(elapsed_sec)
        self._n += 1
        step_index = self._n - 1        # 0=reset 初始帧；k=第 k 步执行后的新状态
        state = pf.state
        if self.mode == "lose" and step_index >= self.lose_in:
            # 脚本化：到达失败步后漏怪导致目标耐久归零
            state.life_points = 0
        return pf

    def is_cleared(self):
        if self.mode != "win":
            return False
        return (self._n - 1) >= self.win_in

    # 其余全部委托给底层 mock 战局
    def on_after_step(self, command_or_plan, plan_result):
        return self.base.on_after_step(command_or_plan, plan_result)

    def regen(self):
        return self.base.regen()

    def card_slot(self, name):
        return self.base.card_slot(name)

    def deployed_cell(self, name):
        return self.base.deployed_cell(name)


def build_mock_env(mode="win", stage_id="3-8", win_in=10, lose_in=3,
                   step_dt_sec=1.0):
    # type: (str, str, int, int, float) -> ArknightsEnv
    """装配一套自包含 mock 环境（含 Agent 决策组件），可直接 run_episode()。"""
    from action.action_executor import ActionExecutor
    from action.adb_controller import MockADBController
    from action.config import load_action_config
    from agent.config import load_agent_config
    from agent.decision_loop import MockKnowledge, MockPerception
    from agent.fast_reactor import MockFastReactor
    from agent.latent_bridge import MockLatentBridge
    from agent.slow_thinker import MockSlowThinker

    cfg = load_agent_config()
    base = MockPerception(stage_id=stage_id)
    perception = ScriptedPerception(base, mode=mode, win_in=win_in, lose_in=lose_in)
    executor = ActionExecutor(
        MockADBController(), config=load_action_config(),
        card_slot_resolver=base.card_slot,
        deployed_cell_resolver=base.deployed_cell,
        real_sleep=False)

    terminal_step = win_in if mode == "win" else max(win_in, lose_in + 1)
    return ArknightsEnv(
        perception=perception, executor=executor,
        knowledge=MockKnowledge(), slow=MockSlowThinker(config=cfg),
        bridge=MockLatentBridge(config=cfg), fast=MockFastReactor(config=cfg),
        config=cfg, stage_id=stage_id, step_dt_sec=step_dt_sec,
        max_steps=terminal_step, backend="mock")


def run_mock_episode(mode="win", stage_id="3-8", win_in=10, lose_in=3):
    """便捷入口：构建并跑完一局，返回 EpisodeLog。"""
    env = build_mock_env(mode=mode, stage_id=stage_id, win_in=win_in, lose_in=lose_in)
    return env.run_episode(stage_id=stage_id)
