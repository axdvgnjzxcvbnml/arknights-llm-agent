"""env 包：环境封装（Gym 风格调度接口 / mock 对局 / 评估奖励），纯 CPU、不产生梯度。

import env 只依赖 pydantic 与 action（无 numpy/torch/transformers）；
perception/agent 等在 mock_env 工厂函数内延迟导入。
"""

from .arknights_env import (ArknightsEnv, EnvStep, EpisodeLog, coerce_plan,
                            render_episode_report)
from .mock_env import ScriptedPerception, build_mock_env, run_mock_episode
from .reward import EpisodeReward, RewardBreakdown, RewardConfig, RewardItem

__all__ = [
    "ArknightsEnv",
    "EnvStep",
    "EpisodeLog",
    "coerce_plan",
    "render_episode_report",
    "ScriptedPerception",
    "build_mock_env",
    "run_mock_episode",
    "RewardConfig",
    "RewardItem",
    "RewardBreakdown",
    "EpisodeReward",
]
