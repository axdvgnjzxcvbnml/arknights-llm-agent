"""perception 包：视觉解析（截屏 / CV 快通道 / VLM 慢通道 / 状态转文本）。

导入本包只装配 numpy 级别的截屏/组装/mock 能力；torch / ultralytics / paddleocr /
VLM 等重依赖在对应模块方法内延迟导入，不在 import 期拉起 GPU 栈。
"""

from .config import DEFAULT_CONFIG_PATH, load_perception_config
from .schemas import GameState
from .screen_capture import (ADBScreenCapture, MockScreenCapture, ScreenCapture,
                             get_screen_capture)
from .state_parser import MockStateParser, SpawnTracker, StateParser

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "load_perception_config",
    "GameState",
    "ScreenCapture",
    "ADBScreenCapture",
    "MockScreenCapture",
    "get_screen_capture",
    "StateParser",
    "MockStateParser",
    "SpawnTracker",
]
