# TODO-V100: YOLOv8 真实检测需要训练后的权重 weights/yolov8n_arknights.pt 与 GPU 推理。
# 第一版不做全图实时敌人检测：敌情由 state_parser.SpawnTracker 按"关卡敌情表+计时推算"，
# 本模块只预留 confirm_spawn 做"敌人是否已出现"的轻量确认，把计时结果升级为 CV 确认。
"""YOLO 干员/敌人检测（骨架）+ 波次出现确认。

训练数据来源（V100 阶段）：
- 敌人/干员裁剪图来自 PRTS Wiki 图片（仅本地训练用，**不入库**）；
- 真机/MuMu 录屏抽帧后用标注工具（如 labelImg）标注 bbox + 类别，产出 YOLO 格式数据集；
- 基座 yolov8n，在 V100(sm_70) 上微调；检测类别见 configs/models.yolo.classes。

import 本模块不拉起 ultralytics/torch（在真实 detect 内延迟导入）。
"""

import os
from typing import List, Optional

import numpy as np

from .config import DEFAULT_CONFIG_PATH, load_perception_config
from .schemas import BBox, DetectedObject

__all__ = ["YoloDetector", "MockDetector", "DetectorError"]


class DetectorError(RuntimeError):
    """检测器错误（权重缺失/引擎未装/推理失败）。"""


class YoloDetector(object):
    """YOLOv8 真实检测骨架；CPU 沙箱无权重，detect 抛 NotImplementedError。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_perception_config(config_path)
        yolo = cfg.get("models", {}).get("yolo", {})
        coords = cfg.get("coords", {})
        self.weights = yolo.get("weights", "weights/yolov8n_arknights.pt")
        self.conf_threshold = float(yolo.get("conf_threshold", 0.35))
        self.iou_threshold = float(yolo.get("iou_threshold", 0.5))
        self.device = yolo.get("device", "cpu")
        self.classes = list(yolo.get("classes", []))
        # 入场确认 ROI。注意：configs 中为【占位坐标，待真机校准】，不同分辨率/关卡
        # 入口位置不同，真机阶段必须用实测坐标覆盖，不能直接拿占位值上线。
        self.confirm_roi = tuple(
            coords.get("enemy_confirm_region", coords.get("map_region",
                                                          [0, 0, 0, 0])))
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        if not os.path.exists(self.weights):
            raise NotImplementedError(
                "TODO-V100: 未找到 YOLO 权重 %s。需在 V100 上用 PRTS 敌人图片 + 真机截图"
                "标注数据微调 yolov8n 后导出到该路径（configs/perception.yaml: "
                "models.yolo.weights）。" % self.weights)
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectorError(
                "未安装 ultralytics，无法加载 YOLO 权重。真机/V100 环境 pip install "
                "ultralytics。原始错误：%s" % exc)
        # TODO-V100: device 改 cuda:0；首次加载后可常驻，推理目标 ≤30ms/帧
        self._model = YOLO(self.weights)
        return self._model

    @staticmethod
    def _crop(frame, roi):
        if roi is None:
            return frame
        x1, y1, x2, y2 = (int(v) for v in roi)
        h, w = frame.shape[:2]
        x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
        y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
        return frame[y1:y2, x1:x2]

    def detect(self, frame, roi=None):
        # type: (np.ndarray, Optional[tuple]) -> List[DetectedObject]
        """通用目标检测；返回 DetectedObject 列表。真实推理 TODO-V100。"""
        raise NotImplementedError(
            "TODO-V100: 用 _load_model()(crop, conf=..., iou=..., device=...) 推理，"
            "把 ultralytics 结果 boxes.xyxy/conf/cls 映射成 DetectedObject。训练数据="
            "PRTS 敌人图片 + 真机截图标注。")

    def confirm_spawn(self, enemy_name, frame):
        # type: (str, np.ndarray) -> bool
        """确认某敌人是否已在入场 ROI 出现。True=确认，False=未检测到/置信不足。

        典型用法（与 SpawnTracker 联动，把 estimated 升级为 cv）：
            ok = detector.confirm_spawn("碎骨", frame)
            SpawnTracker.update(plan, elapsed, confirmations={"碎骨": ok})
        """
        if not enemy_name:
            return False
        try:
            objects = self.detect(frame, roi=self.confirm_roi)
        except NotImplementedError:
            raise
        for obj in objects:
            if obj.label == enemy_name and obj.confidence >= self.conf_threshold:
                return True
        return False


class MockDetector(YoloDetector):
    """固定检测结果：左侧入场区 3 个重装敌人（确定性，可配），用于 CPU 闭环。"""

    # (label, conf, 相对 confirm_roi 的归一化 bbox)
    DEFAULT_OBJECTS = [
        ("重装敌人", 0.92, (0.10, 0.30, 0.30, 0.70)),
        ("重装敌人", 0.90, (0.32, 0.32, 0.52, 0.72)),
        ("重装敌人", 0.88, (0.54, 0.34, 0.74, 0.74)),
    ]

    def __init__(self, objects=None, config=None, config_path=DEFAULT_CONFIG_PATH):
        super(MockDetector, self).__init__(config=config, config_path=config_path)
        self._mock_objects = list(objects) if objects is not None else list(self.DEFAULT_OBJECTS)

    def detect(self, frame, roi=None):
        use_roi = tuple(roi) if roi is not None else self.confirm_roi
        x1, y1, x2, y2 = use_roi
        rw, rh = max(1, x2 - x1), max(1, y2 - y1)
        out = []
        for label, conf, (nx1, ny1, nx2, ny2) in self._mock_objects:
            out.append(DetectedObject(
                label=label, confidence=conf, source="mock",
                bbox=BBox(x1=x1 + int(nx1 * rw), y1=y1 + int(ny1 * rh),
                          x2=x1 + int(nx2 * rw), y2=y1 + int(ny2 * rh))))
        return out

    def confirm_spawn(self, enemy_name, frame):
        if not enemy_name:
            return False
        return any(obj.label == enemy_name and obj.confidence >= self.conf_threshold
                   for obj in self.detect(frame))
