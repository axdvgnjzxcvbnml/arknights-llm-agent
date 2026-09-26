# 费用 OCR 在 CPU 即可运行（PaddleOCR），V100 上可切 GPU 加速；本沙箱不安装 paddle，
# 真实识别在真机/装了 paddleocr 的环境执行，CPU 侧用 MockOCRCostReader 打通链路。
"""费用识别：从截图费用 ROI 读当前部署费用（DP）。

- OCRCostReader：PaddleOCR 真实实现，ROI 从 configs/perception.yaml 的 coords.cost_box 读。
- MockOCRCostReader：返回固定值（也支持注入读数序列用于测试），不依赖 paddle。
- 两帧一致性容错（在基类）：费用正常随时间回复只增不减，相邻帧**小幅增长（≤10）或持平**
  视为正常；只有"读数下降（疑似花屏/把别的数字读成费用）"或"单帧跳变 >10（疑似误识别）"
  才判 state=uncertain，confidence 压低，调用方"先别据此决策"；阈值可配
  （models.ocr.max_single_frame_jump，默认 10）。本帧读不到数字判 state=missing。

import 本模块不拉起 paddleocr：引擎在首次识别时延迟导入。
"""

import re
from typing import List, Optional, Tuple

import numpy as np

from .config import DEFAULT_CONFIG_PATH, load_perception_config
from .schemas import CostStatus

__all__ = ["OCRError", "BaseCostReader", "OCRCostReader", "MockOCRCostReader"]

# 两帧不一致时把置信度压到该上限，明确表达"存疑"
_UNCERTAIN_CONF_CAP = 0.4
# 单帧费用跳变阈值：|new-last| 超过该值视为误识别；可用配置 models.ocr.max_single_frame_jump 覆盖
_DEFAULT_MAX_JUMP = 10


class OCRError(RuntimeError):
    """OCR 引擎/识别链路错误。"""


def _crop_roi(frame, roi):
    # type: (np.ndarray, tuple) -> np.ndarray
    x1, y1, x2, y2 = (int(v) for v in roi)
    h, w = frame.shape[:2]
    x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
    y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        raise OCRError("费用 ROI 非法或超出画面：%r（画面 %dx%d）" % (roi, w, h))
    return frame[y1:y2, x1:x2]


class BaseCostReader(object):
    """统一 read(frame)->CostStatus；子类只实现 _recognize_digit(crop)->(int|None, conf)。"""

    reading_source = "cv"

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH, roi=None):
        cfg = config or load_perception_config(config_path)
        self.roi = tuple(roi if roi is not None else cfg["coords"]["cost_box"])
        self._max_jump = int(cfg.get("models", {}).get("ocr", {})
                             .get("max_single_frame_jump", _DEFAULT_MAX_JUMP))
        self._last = None  # type: Optional[int]

    def reset(self):
        """清空上一帧记忆（开局/重开本关时调用)。"""
        self._last = None

    def _recognize_digit(self, crop):
        # type: (np.ndarray) -> Tuple[Optional[int], float]
        raise NotImplementedError

    def read(self, frame):
        # type: (np.ndarray) -> CostStatus
        crop = _crop_roi(frame, self.roi)
        value, conf = self._recognize_digit(crop)
        if value is None:
            # 读不到：保留上一稳定值供参考，但状态标 missing，不允许当新读数用
            return CostStatus(current=self._last if self._last is not None else 0,
                              confidence=0.0, source=self.reading_source, state="missing")
        if self._last is not None and value != self._last:
            # 费用随时间回复：只增不减。仅当"下降"或"单帧跳变超过阈值"时判存疑；
            # 小幅增长（部署费用自然回复，1 帧 +1~阈值内）与持平都算正常。
            delta = int(value) - int(self._last)
            implausible = (delta < 0) or (abs(delta) > self._max_jump)
            if implausible:
                state = "uncertain"
                conf = min(float(conf), _UNCERTAIN_CONF_CAP)
            else:
                state = "ok"
        else:
            state = "ok"
        self._last = value
        return CostStatus(current=int(value), confidence=float(conf),
                          source=self.reading_source, state=state)


class OCRCostReader(BaseCostReader):
    """PaddleOCR 费用识别（真实实现，需要安装 paddleocr / paddlepaddle）。"""

    reading_source = "cv"

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH, roi=None):
        super(OCRCostReader, self).__init__(config=config, config_path=config_path, roi=roi)
        cfg = config or load_perception_config(config_path)
        self.lang = cfg.get("models", {}).get("ocr", {}).get("lang", "ch")
        self._ocr = None

    def _get_engine(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise OCRError(
                    "未安装 paddleocr，无法做真实费用识别。CPU 冒烟请用 "
                    "MockOCRCostReader；真机环境 pip install paddleocr paddlepaddle。"
                    " 原始错误：%s" % exc)
            # TODO-V100: V100 环境可传 use_gpu=True（具体参数随 paddleocr 版本适配）
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
        return self._ocr

    @staticmethod
    def _parse_number(ocr_result):
        # type: (object) -> Tuple[Optional[int], float]
        """从 PaddleOCR 返回结构中取置信度最高的整数。

        PaddleOCR 常见结构：[[ [box, (text, score)], ... ]]；不同版本外层略有差异，
        这里做宽容解析：递归找形如 (text, score) 的二元组。
        """
        best = None  # (score, number)

        def walk(node):
            nonlocal best
            if isinstance(node, (list, tuple)):
                # 命中 (text, score) 叶子
                if (len(node) == 2 and isinstance(node[0], str)
                        and isinstance(node[1], (int, float))):
                    text, score = node
                    digits = re.sub(r"\D", "", text)
                    if digits:
                        num = int(digits)
                        if best is None or float(score) > best[0]:
                            best = (float(score), num)
                    return
                for child in node:
                    walk(child)

        walk(ocr_result)
        if best is None:
            return None, 0.0
        return best[1], best[0]

    def _recognize_digit(self, crop):
        engine = self._get_engine()
        try:
            result = engine.ocr(crop, cls=True)
        except Exception as exc:  # paddle 运行期错误统一包装
            raise OCRError("PaddleOCR 识别失败：%s" % exc)
        return self._parse_number(result)


class MockOCRCostReader(BaseCostReader):
    """返回固定费用；可传 values 序列模拟读数变化/漏识别以测试容错。"""

    reading_source = "mock"

    def __init__(self, value=15, confidence=1.0, values=None,
                 config=None, config_path=DEFAULT_CONFIG_PATH, roi=None):
        super(MockOCRCostReader, self).__init__(
            config=config, config_path=config_path, roi=roi)
        self._fixed = int(value)
        self._fixed_conf = float(confidence)
        # values: [15, 15, 16, None, ...]，None 表示本帧读不到
        self._program = list(values) if values is not None else None  # type: Optional[List]

    def _recognize_digit(self, crop):
        if self._program is not None:
            if not self._program:
                return None, 0.0
            v = self._program.pop(0)
            return (None, 0.0) if v is None else (int(v), self._fixed_conf)
        return self._fixed, self._fixed_conf
