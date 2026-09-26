# TODO-V100: 慢思考隐藏态 -> 快反应输入空间的神经投影需在 V100 上实现。
# CPU 侧只提供确定性"伪向量 + 战略意图短文本"的 mock 桥接，不加载任何模型。
"""慢快桥接（Latent Bridge）。

真实设计（TODO-V100）：取慢思考模型最后一层隐状态 h_slow，训练一个线性/MLP 投影
P(·) 到快反应模型的输入空间，快模型据此直接获得"战略意图"，**避免慢模型把结论再序列化成
文字、快模型再读一遍文字**的往返延迟（latent 传递而非 text 往返）。

CPU mock：不接触隐状态，用决策内容生成确定性伪向量（仅用于接口联调/维度校验）+ 一个
短文本 hint（在 mock 中退化为文字承载意图，真实投影落地后 hint 仅作可解释旁路）。
"""

import hashlib
import math
from typing import List

from .config import DEFAULT_CONFIG_PATH, load_agent_config
from .output_schema import AgentDecision, BridgeState

__all__ = ["BaseLatentBridge", "LatentBridgeProjector", "MockLatentBridge"]


class BaseLatentBridge(object):
    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        self.config = config or load_agent_config(config_path)
        self.dim = int(self.config["latent_bridge"].get("dim", 256))

    def project(self, decision):
        # type: (AgentDecision) -> BridgeState
        # 统一约定：decision.hidden_state 有值 -> 神经投影（V100）；
        # None -> 文字桥接 fallback（不加载投影层/模型，CPU 可用）。
        if getattr(decision, "hidden_state", None) is not None:
            return self._project_latent(decision)
        return text_bridge_state(decision, self.dim)

    def _project_latent(self, decision):
        # type: (AgentDecision) -> BridgeState
        raise NotImplementedError


class LatentBridgeProjector(BaseLatentBridge):
    """V100 真实神经投影。CPU 沙箱不可用。

    hidden_state 缺省时 project() 自动退化为文字桥接（见 text_bridge_state），
    因此在慢模型尚未吐出隐状态的阶段，整条链路仍可在 CPU 跑通。
    """

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        super(LatentBridgeProjector, self).__init__(config, config_path)
        self.projector_kind = self.config["latent_bridge"].get("projector", "linear")
        self._proj = None

    def _load(self):
        # TODO-V100: 在 V100 上构建/加载投影层 P: h_slow(dim_slow) -> h_fast(dim_fast)，
        # 参数来自慢快联合训练（见 training/，非 RL）。需要真实隐藏态与两块 GPU 模型。
        raise NotImplementedError(
            "TODO-V100: 慢->快隐状态投影需在 V100 上加载（projector=%s, dim=%d）；"
            "CPU 侧请使用 MockLatentBridge。" % (self.projector_kind, self.dim))

    def _project_latent(self, decision):
        # 仅当 decision.hidden_state 有值时才会走到这里（见 BaseLatentBridge.project）。
        if self._proj is None:
            self._load()
        # TODO-V100: 用 self._proj 把 decision.hidden_state 投影为快模型输入张量，
        # 并填充 BridgeState.vector（hint 退为可解释旁路），source="projected"。
        raise NotImplementedError("TODO-V100: 隐状态投影在 V100 上实现。")


def text_bridge_state(decision, dim):
    # type: (AgentDecision, int) -> BridgeState
    """文字桥接 fallback：无隐状态时用决策内容生成确定性伪向量 + 战略意图短文本。

    同时供 MockLatentBridge 与 LatentBridgeProjector 的 fallback 分支使用，
    保证"有/无隐状态"两条路径产出的 BridgeState 形状一致。
    """
    seed_text = "%s|%s" % (decision.decision_id,
                           decision.reasoning.summary or "wait")
    vec = MockLatentBridge._pseudo_vector(seed_text, dim)
    first = decision.plan.actions[0] if decision.plan.actions else None
    if first is None:
        hint = "战略意图：本步等待观察。"
    elif first.action == "deploy":
        dir_cn = {"up": "上", "down": "下", "left": "左", "right": "右"}
        hint = "战略意图：部署 %s 到 %s 朝%s（%s）。" % (
            first.operator_id, first.grid_pos,
            dir_cn.get(first.direction, first.direction),
            decision.reasoning.summary)
    elif first.action == "skill":
        hint = "战略意图：开启 %s 的技能 %d。" % (
            first.operator_id, first.skill_id)
    elif first.action == "retreat":
        hint = "战略意图：撤退 %s 以回收部署位。" % first.operator_id
    else:
        hint = "战略意图：等待 %dms。" % (first.duration_ms or 0)
    return BridgeState(decision_id=decision.decision_id, vector=vec,
                       dim=dim, hint=hint, source="mock")


class MockLatentBridge(BaseLatentBridge):
    """确定性伪向量 + 战略意图短文本（纯 CPU，可复现）。

    mock 慢思考不产出 hidden_state（恒 None），故恒走文字桥接 fallback。
    """

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        super(MockLatentBridge, self).__init__(config, config_path)

    def project(self, decision):
        return text_bridge_state(decision, self.dim)

    @staticmethod
    def _pseudo_vector(seed_text, dim):
        # type: (str, int) -> List[float]
        # 取 sha256 摘要循环填充，再做简单正弦混合，确定性且对输入敏感；仅接口联调用。
        digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
        raw = []
        i = 0
        while len(raw) < dim:
            raw.append(digest[i % len(digest)] / 255.0)
            i += 1
        return [round(0.5 * raw[j] + 0.5 * math.sin(j * 0.37 + raw[j] * 6.28), 6)
                for j in range(dim)]
