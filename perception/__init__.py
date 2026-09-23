"""perception 包：视觉解析（截屏 / CV 快通道 / VLM 慢通道 / 状态转文本）。

导入本包只装配 numpy 级别的截屏/组装/mock 能力；torch / ultralytics / paddleocr /
VLM 等重依赖在对应模块方法内延迟导入，不在 import 期拉起 GPU 栈。
"""

from .config import DEFAULT_CONFIG_PATH, load_perception_config
from .detector_yolo import MockDetector, YoloDetector
from .map_parser import MapParser, MockMapParser
from .ocr_cost import (BaseCostReader, MockOCRCostReader, OCRCostReader, OCRError)
from .schemas import GameState, VLMAnalysis
from .screen_capture import (ADBScreenCapture, MockScreenCapture, ScreenCapture,
                             get_screen_capture)
from .state_parser import MockStateParser, SpawnTracker, StateParser
from .state_to_text import state_to_text
from .vlm_analyzer import MockVLMAnalyzer, VLMAnalyzer, state_to_context

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
    "BaseCostReader",
    "OCRCostReader",
    "MockOCRCostReader",
    "OCRError",
    "MapParser",
    "MockMapParser",
    "YoloDetector",
    "MockDetector",
    "VLMAnalyzer",
    "MockVLMAnalyzer",
    "VLMAnalysis",
    "state_to_context",
    "state_to_text",
]
