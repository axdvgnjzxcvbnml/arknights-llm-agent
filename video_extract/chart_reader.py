# VLM 读图表：V100 上用 Qwen3-VL-8B 或 UI-TARS-7B，
#   对抽帧图片识别 Excel 数据表 / DPS 对比 / 强度榜，输出结构化 JSON。
#   模型名/设备在 video_extract/config.yaml 的 vlm 段配置。
#   CPU 侧：依赖/模型未配置时抛 ChartReadError，不静默降级。
"""VLM 读图表：抽帧图片 -> 结构化图表数据。

输出统一形如：
    {"timestamp": 12.5, "type": "table", "operator": "银灰",
     "data": {...}, "confidence": 0.0, "frame_path": ..., "evidence": "retrieved:video_frame"}
- VLMChartReader：真实推理实现（_load_model + read_chart 完整），V100 上运行；
  CPU/无模型/无依赖时抛 ChartReadError。已吸收两个实测坑（示例字面量复制、markdown fence）。
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
    """Qwen3-VL/UI-TARS 真实读图；V100 上运行，CPU/无模型/无依赖时抛 ChartReadError。

    已知坑（WorkBuddy 5060 Ti 实测）：
    1. VLM 会照抄 prompt 里的示例字面量（把 operator 输出成"主角干员名"）。
       对策：prompt 里明确"示例仅展示 JSON 结构，不要复制示例中的任何文字内容"，
       后处理校验 operator/title 字段是否等于示例字面量，命中则丢弃并降置信度。
    2. VLM 输出外层带 markdown ```json fence。
       对策：_strip_json_fence() 用正则剥离 ```json 和 ``` 后再 json.loads。
    """

    # prompt 里用的示例字面量黑名单（后处理校验用）
    _EXAMPLE_LITERALS = {"主角干员名", "示例干员", "干员名", "example_operator",
                          "示例标题", "example_title", "T0示例"}

    SYSTEM_PROMPT = (
        "你是明日方舟视频图表识别助手。请分析输入图片中的图表内容，"
        "输出严格的 JSON。\n"
        "重要规则：\n"
        "1. 只输出 JSON，不要输出任何解释文字。\n"
        "2. 下方的示例仅展示 JSON 结构和字段名，不要复制示例中的任何文字内容"
        "（包括干员名、标题、数值）。必须根据图片实际内容填写。\n"
        "3. 如果图片中没有可识别的图表，输出 {\"chart_type\": \"unknown\", \"data\": {}}。\n"
        "4. 数值字段必须是数字，不要加单位或千分位逗号。"
    )

    EXAMPLE_JSON = (
        '{"chart_type": "table", "operator": "（从图片识别的实际干员名）", '
        '"confidence": 0.9, "data": {"title": "（图表实际标题）", '
        '"columns": ["列1", "列2"], "rows": [{"列1": "值1", "列2": "值2"}]}}'
    )

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        v = cfg.get("vlm", {})
        self.model_name = v.get("model", "")
        self.device = v.get("device", "cpu")
        self.dtype = v.get("dtype", "float16")
        self.confidence_threshold = float(v.get("confidence_threshold", 0.6))
        self.max_new_tokens = int(v.get("max_new_tokens", 1024))
        self._processor = None
        self._model = None

    def _load_model(self):
        """加载 VLM processor + model，缓存到 self._processor / self._model。

        V100 上：Qwen3-VL-8B，device=cuda，dtype=float16（V100 sm_70 不支持 bf16）。
        CPU/无模型/无依赖时抛 ChartReadError（或 NotImplementedError 表示需 V100 配置）。
        """
        if self._model is not None and self._processor is not None:
            return self._processor, self._model
        if not self.model_name:
            raise NotImplementedError(
                "TODO-V100: 未配置 VLM 模型（video_extract/config.yaml vlm.model）。"
                "在 V100 上填 Qwen/Qwen3-VL-8B 或类似 VLM，并设 vlm.backend=qwen3vl、"
                "vlm.device=cuda、vlm.dtype=float16 后再做真实图表识别。")
        try:
            import torch  # noqa: F401  延迟导入，确认 GPU 栈存在
            from transformers import AutoProcessor, AutoModelForVision2Seq
        except ImportError as exc:
            raise ChartReadError(
                "未安装 transformers/torch，无法加载 VLM。V100 环境安装 GPU 版依赖。"
                "原始错误：%s" % exc)
        # 加载 processor/model 到指定 device；Qwen3-VL 用 AutoModelForVision2Seq
        import torch as _torch
        self._processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
        self._model = AutoModelForVision2Seq.from_pretrained(
            self.model_name,
            torch_dtype=getattr(_torch, self.dtype, _torch.float16),
            trust_remote_code=True,
        ).to(self.device).eval()
        return self._processor, self._model

    @staticmethod
    def _strip_json_fence(text):
        """剥离 VLM 输出外层的 markdown ```json ... ``` fence。

        已知坑：VLM 输出常带 ```json 前缀和 ``` 后缀，直接 json.loads 会失败。
        """
        if not text:
            return text
        s = text.strip()
        # 匹配 ```json 或 ``` 开头，``` 结尾
        import re
        m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", s, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 兼容只有开头 fence 没有结尾的情况
        m2 = re.match(r"^```(?:json)?\s*\n?(.*)$", s, re.DOTALL)
        if m2:
            return m2.group(1).strip()
        return s

    @staticmethod
    def _validate_output(parsed):
        """后处理校验：检测 VLM 是否照抄了 prompt 示例字面量。

        已知坑：VLM 会把 operator 输出成"主角干员名"等示例字面量。
        命中则将 chart_type 改为 unknown、confidence 降为 0.0，并返回。
        """
        if not isinstance(parsed, dict):
            return {"chart_type": "unknown", "data": {}, "confidence": 0.0}
        operator = str(parsed.get("operator", ""))
        title = str(parsed.get("data", {}).get("title", "")) if isinstance(parsed.get("data"), dict) else ""
        if operator in VLMChartReader._EXAMPLE_LITERALS or title in VLMChartReader._EXAMPLE_LITERALS:
            # 照抄示例字面量，丢弃内容
            return {"chart_type": "unknown", "data": {}, "confidence": 0.0,
                    "_warning": "VLM 照抄了 prompt 示例字面量，已丢弃"}
        return parsed

    def read_chart(self, frame_path, timestamp_sec):
        # type: (str, float) -> ChartRecord
        if not frame_path or not os.path.exists(frame_path):
            raise ChartReadError("帧图片不存在: %s" % frame_path)
        processor, model = self._load_model()  # CPU/未配置/无依赖时抛 ChartReadError

        # 加载图片
        try:
            from PIL import Image
            image = Image.open(frame_path).convert("RGB")
        except Exception as exc:
            raise ChartReadError("图片加载失败: %s (%s)" % (frame_path, exc))

        # 构造 prompt：系统提示 + 示例（强调不要照抄）
        prompt = "%s\n\n输出格式示例（仅结构参考，不要复制内容）:\n%s\n\n请分析图片：" % (
            self.SYSTEM_PROMPT, self.EXAMPLE_JSON)

        # VLM 推理
        import torch
        inputs = processor(images=image, text=prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            generated = model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        # 解码（只取生成部分，去掉 prompt）
        input_len = inputs["input_ids"].shape[1]
        raw_text = processor.decode(generated[0][input_len:], skip_special_tokens=True)

        # 剥离 markdown fence + 解析 JSON
        cleaned = self._strip_json_fence(raw_text)
        try:
            parsed = json.loads(cleaned)
        except (ValueError, TypeError) as exc:
            # JSON 解析失败，返回 unknown
            return ChartRecord(
                timestamp_sec=timestamp_sec, chart_type="unknown",
                data={"_raw_output": raw_text[:500], "_parse_error": str(exc)},
                confidence=0.0, frame_path=frame_path)

        # 后处理校验：检测照抄示例字面量
        parsed = self._validate_output(parsed)

        chart_type = str(parsed.get("chart_type", "unknown"))
        confidence = float(parsed.get("confidence", 0.0))
        operator = str(parsed.get("operator", ""))
        data = parsed.get("data", {}) if isinstance(parsed.get("data"), dict) else {}

        return ChartRecord(
            timestamp_sec=timestamp_sec, chart_type=chart_type,
            data=data, operator=operator, confidence=confidence,
            frame_path=frame_path)

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
    """按 vlm.backend 选择：qwen3vl=真实 VLM 推理，其余=mock。"""
    cfg = config or load_video_config(config_path)
    backend = cfg.get("vlm", {}).get("backend", "mock")
    if backend == "qwen3vl":
        return VLMChartReader(cfg)
    return MockChartReader(cfg)
