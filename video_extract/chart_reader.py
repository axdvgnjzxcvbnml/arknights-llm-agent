# TODO-V100: 读图表需要视觉语言模型：V100 上用 Qwen3-VL-8B 或 UI-TARS-7B，
#   对抽帧图片识别 Excel 数据表 / DPS 对比 / 强度榜，输出结构化 JSON。
#   模型名/设备在 video_extract/config.yaml 的 vlm 段配置。
"""VLM 读图表：抽帧图片 -> 结构化图表数据。

输出统一形如：
    {"timestamp": 12.5, "type": "table", "operator": "银灰",
     "data": {...}, "confidence": 0.0, "frame_path": ..., "evidence": "retrieved:video_frame"}
- VLMChartReader：真实推理骨架，CPU/无模型时抛 NotImplementedError(TODO-V100)。
- MockChartReader：在抽帧时间戳里挑最接近"数据表/强度榜"锚点的两帧，产出固定结构，
  时间轴与 mock 抽帧/口播对齐，供 CPU 闭环。

证据：图表数字是"视频画面里显示的内容"，属第三方 UP 主测算，按 retrieved（参考资料）处理，
不是 PRTS/官方事实；structurer 会强制带 BV + 时间戳来源。
"""

import json
import os
from dataclasses import asdict, dataclass, field

from . import DEFAULT_CONFIG_PATH, load_video_config

__all__ = ["ChartRecord", "ChartReadError", "VLMChartReader",
           "MockChartReader", "build_chart_reader"]


class ChartReadError(RuntimeError):
    """图表读取错误：图片缺失、模型/依赖缺失、推理失败。"""


@dataclass
class ChartRecord(object):
    timestamp_sec: float
    chart_type: str                       # table | dps_chart | tier_list | unknown
    data: dict = field(default_factory=dict)
    operator: str = ""
    confidence: float = 0.0
    frame_path: str = ""
    evidence: str = "retrieved:video_frame"

    def to_dict(self):
        return asdict(self)


class VLMChartReader(object):
    """Qwen3-VL/UI-TARS 真实读图骨架；V100 填实现，CPU 抛 TODO-V100。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        v = cfg.get("vlm", {})
        self.model_name = v.get("model", "")
        self.device = v.get("device", "cpu")
        self.confidence_threshold = float(v.get("confidence_threshold", 0.6))

    def _load_model(self):
        if not self.model_name:
            raise NotImplementedError(
                "TODO-V100: 未配置 VLM 模型（video_extract/config.yaml vlm.model）。"
                "在 V100 上填 Qwen3-VL-8B 或 UI-TARS-7B，并设 vlm.backend=qwen3vl、"
                "vlm.device=cuda 后再做真实图表识别。")
        try:
            import torch  # noqa: F401  延迟导入，仅用于确认 GPU 栈存在
            from transformers import AutoModelForVision2Seq, AutoProcessor  # noqa: F401
        except ImportError as exc:
            raise ChartReadError(
                "未安装 transformers/torch，无法加载 VLM。V100 环境安装 GPU 版依赖。"
                "原始错误：%s" % exc)
        # TODO-V100: 加载 processor/model 到 cuda；构造"把表格/榜单转成严格 JSON"的提示词
        raise NotImplementedError(
            "TODO-V100: 在此加载 %s 并实现图像 -> 结构化 JSON（表头识别、数值抽取、"
            "强度榜档位解析），置信度低于 %.2f 的丢弃。"
            % (self.model_name, self.confidence_threshold))

    def read_chart(self, frame_path, timestamp_sec):
        # type: (str, float) -> ChartRecord
        if not frame_path or not os.path.exists(frame_path):
            raise ChartReadError("帧图片不存在: %s" % frame_path)
        self._load_model()  # CPU/未配置时抛 NotImplementedError(TODO-V100)
        raise NotImplementedError(  # 防御：_load_model 未抛时仍不给假结果
            "TODO-V100: 调用 VLM 推理，解析 table/dps_chart/tier_list 为 ChartRecord。")

    def read_all(self, frame_records, out_json=None):
        results = []
        for fr in _iter_frames(frame_records):
            if fr.get("timestamp_sec", 0) <= 0:
                continue
            rec = self.read_chart(fr.get("frame_path", ""), fr.get("timestamp_sec", 0.0))
            if rec and rec.confidence >= self.confidence_threshold:
                results.append(rec)
        if out_json:
            _write_charts(results, out_json)
        return results


class MockChartReader(object):
    """固定图表：在帧时间戳中就近选两帧，分别放"输出数据表"和"强度榜"。"""

    # 期望出现图表的时间锚点（秒），会吸附到最近的真实抽帧时间戳
    TABLE_ANCHOR = 12.0
    TIER_ANCHOR = 21.0

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        self.confidence_threshold = float(
            cfg.get("vlm", {}).get("confidence_threshold", 0.6))

    @staticmethod
    def _nearest_frame(frame_records, anchor):
        best = None
        best_gap = None
        for fr in _iter_frames(frame_records):
            ts = float(fr.get("timestamp_sec", 0.0))
            gap = abs(ts - anchor)
            if best_gap is None or gap < best_gap:
                best_gap = gap
                best = fr
        return best

    def read_all(self, frame_records, out_json=None):
        results = []
        table_frame = self._nearest_frame(frame_records, self.TABLE_ANCHOR)
        tier_frame = self._nearest_frame(frame_records, self.TIER_ANCHOR)

        if table_frame is not None:
            results.append(ChartRecord(
                timestamp_sec=float(table_frame.get("timestamp_sec", self.TABLE_ANCHOR)),
                chart_type="table",
                operator="银灰",
                confidence=0.93,
                frame_path=table_frame.get("frame_path", ""),
                data={
                    "title": "危机合约干员输出测算",
                    "columns": ["干员", "DPS", "DPH", "攻击间隔"],
                    "rows": [
                        {"干员": "银灰", "DPS": 1820, "DPH": 880, "攻击间隔": 1.2},
                        {"干员": "陈", "DPS": 1560, "DPH": 760, "攻击间隔": 1.1},
                    ],
                    "focus": {"干员": "银灰", "DPS": 1820, "DPH": 880},
                },
            ))
        if tier_frame is not None and tier_frame is not table_frame:
            results.append(ChartRecord(
                timestamp_sec=float(tier_frame.get("timestamp_sec", self.TIER_ANCHOR)),
                chart_type="tier_list",
                operator="银灰",
                confidence=0.9,
                frame_path=tier_frame.get("frame_path", ""),
                data={
                    "title": "本期危机合约强度榜",
                    "tiers": {"T0": ["银灰"], "T1": ["陈"]},
                    "focus": {"干员": "银灰", "tier": "T0"},
                },
            ))
        if out_json:
            _write_charts(results, out_json)
        return results


def _iter_frames(frame_records):
    """兼容 FrameRecord dataclass 列表或 dict 列表。"""
    for fr in frame_records or []:
        if isinstance(fr, dict):
            yield fr
        else:
            yield getattr(fr, "__dict__", None) or {"timestamp_sec": getattr(fr, "timestamp_sec", 0.0),
                                                    "frame_path": getattr(fr, "frame_path", "")}


def _write_charts(charts, out_json):
    d = os.path.dirname(out_json)
    if d:
        os.makedirs(d, exist_ok=True)
    payload = [c.to_dict() if isinstance(c, ChartRecord) else c for c in charts]
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def build_chart_reader(config=None, config_path=DEFAULT_CONFIG_PATH):
    """按 vlm.backend 选择：qwen3vl=真实(TODO-V100)，其余=mock。"""
    cfg = config or load_video_config(config_path)
    backend = cfg.get("vlm", {}).get("backend", "mock")
    if backend == "qwen3vl":
        return VLMChartReader(cfg)
    return MockChartReader(cfg)
