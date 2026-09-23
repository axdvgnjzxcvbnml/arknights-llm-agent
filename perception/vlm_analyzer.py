# TODO-V100: VLM 慢通道需 GPU，V100 上接 Qwen3-VL-8B 或 UI-TARS-7B；CPU 沙箱用 Mock。
"""VLM 慢通道：截图 + GameState(JSON) -> 局势理解 / 战略建议 / 引用解释。

- VLMAnalyzer：真实骨架（TODO-V100），约 2s 触发一次，不阻塞快通道微操。
- MockVLMAnalyzer：依据 GameState 生成确定性分析，用于 CPU 端到端闭环。

输出为严格 Pydantic 模型 VLMAnalysis；VLM 判断恒 level=inferred（模型推断，非事实），
引用通过 EvidenceRef 标注 fact/retrieved/inferred。import 本模块不拉起 torch/transformers。
"""

import json
import time
from typing import Optional

import numpy as np

from .schemas import EvidenceRef, GameState, VLMAnalysis

__all__ = ["VLMAnalyzer", "MockVLMAnalyzer", "state_to_context"]


def state_to_context(state):
    # type: (GameState) -> str
    """把结构化状态序列化为紧凑 JSON，作为 VLM 文本上下文。"""
    return json.dumps(state.model_dump(mode="json"), ensure_ascii=False,
                      separators=(",", ":"))


class VLMAnalyzer(object):
    """VLM 真实接口骨架。"""

    def __init__(self, model_name="", device="cuda:0", interval_sec=2.0):
        self.model_name = model_name
        self.device = device
        self.interval_sec = interval_sec
        self._model = None
        self._last_run = -1e9

    def _load_model(self):
        if self._model is not None:
            return self._model
        if not self.model_name:
            raise NotImplementedError(
                "TODO-V100: 未配置 VLM 模型（configs/perception.yaml: models.vlm.model）。"
                "在 V100 上接 Qwen3-VL-8B 或 UI-TARS-7B，并实现图像+文本编码与结构化解析。")
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForVision2Seq, AutoProcessor  # noqa: F401
        except ImportError as exc:
            raise NotImplementedError(
                "TODO-V100: 缺少 transformers/torch，无法加载 VLM %s：%s"
                % (self.model_name, exc))
        raise NotImplementedError(
            "TODO-V100: 在此加载 %s（device=%s），实现 chat(image, state JSON)->"
            "VLMAnalysis JSON，并约束输出符合 perception.schemas.VLMAnalysis。"
            % (self.model_name, self.device))

    def due(self, now=None):
        # type: (Optional[float]) -> bool
        """节流：距上次分析是否已到 interval_sec。"""
        now = time.time() if now is None else now
        return (now - self._last_run) >= self.interval_sec

    def analyze(self, frame, state):
        # type: (Optional[np.ndarray], GameState) -> VLMAnalysis
        """输入截图 + GameState，输出 VLMAnalysis。真实推理 TODO-V100。"""
        self._load_model()  # CPU/未配置时先抛 NotImplementedError(TODO-V100)
        if frame is None:
            raise ValueError("真实 VLM 分析需要游戏截图 frame，不能为 None")
        raise NotImplementedError  # _load_model 已实现后再补后处理


class MockVLMAnalyzer(VLMAnalyzer):
    """依据状态生成确定性的局势分析，无 GPU/模型依赖。"""

    # 敌人类型 -> 应对建议（关键词级规则，仅 mock，真实建议由 VLM 结合检索生成）
    _COUNTER_HINTS = (
        ("重装", "重装敌人防御高、弱法术", "优先部署术师应对重装"),
    )

    def __init__(self):
        super(MockVLMAnalyzer, self).__init__(model_name="", device="cpu",
                                              interval_sec=2.0)

    def analyze(self, frame, state):  # type: ignore[override]
        cost = state.cost.current if state.cost is not None else 0
        enemy_desc = "、".join(
            "%s%d个(%s)" % (e.name, e.observed_count, e.position_hint or "未知方向")
            for e in state.enemies_on_field) or "暂未观察到敌人"
        side = "右" if any("右" in e.position_hint for e in state.enemies_on_field) else "左"
        situation = ("当前费用%d，%s侧敌情：%s；波次为%s，局面偏防守，先稳住防线再展开。"
                     % (cost, side, enemy_desc,
                        "真实时间轴" if state.timing_source == "annotated" else "计时估算"))

        advice = "先下先锋回费、补狙击/医疗维持阵线。"
        # 注意：CV 读数不在此作为 fact 引用——它在状态报告的 cv/mock 分级区单独标注，
        # 这里只放真正的外部知识引用（PRTS 攻略 retrieved）。
        evidence = []
        risks = list(state.notes)
        names = " ".join(e.name for e in state.enemies_on_field)
        for key, fact, hint in self._COUNTER_HINTS:
            if key in names:
                advice = "建议" + hint + "，随后补医疗与对空输出。"
                evidence.append(EvidenceRef(source="PRTS攻略", detail=fact,
                                            evidence="retrieved"))
                break

        return VLMAnalysis(
            situation=situation, strategic_advice=advice, confidence=0.6,
            evidence=evidence, analyzer="mock", risks=risks, timestamp=time.time())
