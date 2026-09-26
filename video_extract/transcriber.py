# TODO-V100: 真实口播转写需要 ASR 模型与算力：
#   V100 上用 faster-whisper（large-v3, device=cuda, compute_type=float16），
#   或本地 whisper；模型名/设备在 video_extract/config.yaml 的 asr 段配置。
"""ASR 口播转写：音频 -> 带时间戳的文本片段。

输出统一为 [{"start": float, "end": float, "text": str}, ...]（秒）。
- WhisperTranscriber：真实推理骨架，CPU/无模型时抛 NotImplementedError(TODO-V100)。
- MockTranscriber：固定口播文本（围绕银灰/DPS/强度榜，便于对齐下游图表），CPU 闭环用。

import 本模块不拉起 whisper/torch（延迟到真实 transcribe 内）。
"""

import json
import os
from dataclasses import asdict, dataclass

from . import DEFAULT_CONFIG_PATH, load_video_config

__all__ = ["TranscriptSegment", "TranscriberError",
           "WhisperTranscriber", "MockTranscriber", "build_transcriber"]


class TranscriberError(RuntimeError):
    """转写错误：音频缺失、模型/依赖缺失、推理失败。"""


@dataclass
class TranscriptSegment(object):
    start: float
    end: float
    text: str

    def to_dict(self):
        return asdict(self)


class WhisperTranscriber(object):
    """faster-whisper 真实转写骨架；V100 上填实现，CPU 抛 TODO-V100。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        a = cfg.get("asr", {})
        self.model_name = a.get("model", "")
        self.device = a.get("device", "cpu")
        self.compute_type = a.get("compute_type", "int8")
        self.language = a.get("language", "zh")
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        if not self.model_name:
            raise NotImplementedError(
                "TODO-V100: 未配置 ASR 模型（video_extract/config.yaml asr.model）。"
                "在 V100 上填 faster-whisper large-v3 等，并设 asr.backend=whisper、"
                "asr.device=cuda、compute_type=float16 后再运行真实转写。")
        try:
            from faster_whisper import WhisperModel  # 延迟导入
        except ImportError as exc:
            raise TranscriberError(
                "未安装 faster-whisper，无法做真实转写。V100 环境 pip install "
                "faster-whisper。原始错误：%s" % exc)
        # TODO-V100: device=cuda；大模型可常驻，长音频按 VAD 分段控制显存
        self._model = WhisperModel(self.model_name, device=self.device,
                                   compute_type=self.compute_type)
        return self._model

    def transcribe(self, audio_path, out_json=None):
        # type: (str, str) -> list
        if not audio_path or not os.path.exists(audio_path):
            raise TranscriberError("音频文件不存在: %s" % audio_path)
        model = self._load_model()  # CPU/未配置时在此抛 NotImplementedError(TODO-V100)
        # TODO-V100: 启用 word_timestamps/语音活动检测，把 segment 映射成统一片段。
        segments, _info = model.transcribe(
            audio_path, language=self.language, vad_filter=True,
            word_timestamps=True)
        results = [TranscriptSegment(start=round(seg.start, 3),
                                     end=round(seg.end, 3),
                                     text=seg.text.strip()).to_dict()
                   for seg in segments]
        if out_json:
            _write_segments(results, out_json)
        return results


class MockTranscriber(object):
    """固定假口播（确定性），不读取真实音频；时间轴刻意覆盖两张 mock 图表的时刻。"""

    DEFAULT_SEGMENTS = [
        TranscriptSegment(0.0, 6.0, "我们先看这一期危机合约的干员输出环境。"),
        TranscriptSegment(8.0, 16.0,
                          "银灰在这张图的清杂和爆发都很顶，配合三技能真银斩，"
                          "我给的DPS大概一千八百二，单发伤害DPH八百八。"),
        TranscriptSegment(18.0, 24.0,
                          "综合持续输出、爆发和泛用性，我把银灰放在T0这个档位。"),
        TranscriptSegment(26.0, 30.0, "当然具体还是要看关卡词条和你有没有合适的拐。"),
    ]

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        self.language = cfg.get("asr", {}).get("language", "zh")

    def transcribe(self, audio_path=None, out_json=None):
        # type: (str, str) -> list
        results = [s.to_dict() for s in self.DEFAULT_SEGMENTS]
        if out_json:
            _write_segments(results, out_json)
        return results


def _write_segments(segments, out_json):
    d = os.path.dirname(out_json)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)


def build_transcriber(config=None, config_path=DEFAULT_CONFIG_PATH):
    """按 asr.backend 选择实现：whisper=真实(TODO-V100)，其余=mock。"""
    cfg = config or load_video_config(config_path)
    backend = cfg.get("asr", {}).get("backend", "mock")
    if backend == "whisper":
        return WhisperTranscriber(cfg)
    return MockTranscriber(cfg)
