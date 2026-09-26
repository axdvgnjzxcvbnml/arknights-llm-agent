# TODO-V100: 快反应真实推理需要 V100（MiniCPM 级小模型，单步目标 <150ms）。
# CPU 沙箱不加载模型；真实 react raise NotImplementedError。import 不拉起 transformers。
"""快反应模型：慢思考战略意图（BridgeState）+ 当前屏幕状态 -> 可立即执行的 FastCommand。

与慢思考的分工：慢思考负责"打哪、为什么"（秒级、可解释），快反应负责"这一拍能不能做、
先做哪个"（毫秒级）。它会用**当前帧**对慢思考给出的动作做即时可行性裁剪：
费用不够 / 干员不在手牌 / 格子被占或不可部署 / 技能未就绪的动作被丢弃并写明原因，
全部不可执行时退化为一个短 wait，绝不下达乱点的指令。

- FastReactorMiniCPM：V100 真实实现（TODO-V100）；
- MockFastReactor：纯 CPU 规则裁剪，确定性，用于全链路联调。
"""

import time
from typing import List, Optional, Tuple

from action.action_space import Action, ActionPlan

from .config import DEFAULT_CONFIG_PATH, load_agent_config
from .output_schema import AgentDecision, BridgeState, FastCommand

__all__ = ["BaseFastReactor", "FastReactorMiniCPM", "MockFastReactor"]


class BaseFastReactor(object):
    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        self.config = config or load_agent_config(config_path)
        self.deadline_ms = int(
            self.config["models"]["fast"].get("react_deadline_ms", 150))

    def react(self, state, decision, bridge=None):
        # type: (object, AgentDecision, Optional[BridgeState]) -> FastCommand
        raise NotImplementedError


class FastReactorMiniCPM(BaseFastReactor):
    """V100 快反应真实实现。CPU 沙箱不可用。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        super(FastReactorMiniCPM, self).__init__(config, config_path)
        self.model_name = self.config["models"]["fast"]["name"]
        self.device = self.config["models"]["fast"].get("device", "cuda:0")

    def _load_model(self):
        # TODO-V100: 在 V100 上加载 MiniCPM 级小模型（fp16；V100 sm_70 不支持 bf16），
        # 接收桥接隐状态 + 当前帧，
        # 生成即时操作序列；要求单步延迟 < react_deadline_ms。
        raise NotImplementedError(
            "TODO-V100: 快反应模型 %s 需在 V100 加载（device=%s，fp16，目标 %dms 内）；"
            "CPU 侧请使用 MockFastReactor。"
            % (self.model_name, self.device, self.deadline_ms))

    def react(self, state, decision, bridge=None):
        self._load_model()
        # TODO-V100: 结合 bridge.vector（隐状态）与当前 GameState 输出 FastCommand。
        raise NotImplementedError("TODO-V100: 快反应生成在 V100 上实现。")


class MockFastReactor(BaseFastReactor):
    """当前帧可行性裁剪（确定性，纯 CPU）。"""

    reactor_name = "mock"

    def react(self, state, decision, bridge=None):
        start = time.time()
        kept = []          # type: List[Action]
        dropped = []       # type: List[str]
        if state is None:
            cmd = FastCommand(
                decision_id=decision.decision_id,
                plan=ActionPlan(actions=[Action(action="wait", duration_ms=500)]),
                dropped=["无当前状态，慢思考动作全部挂起，改为短等待"],
                confidence=0.2, reactor="mock",
                note="快通道：状态缺失，保守等待")
            cmd.react_ms = (time.time() - start) * 1000.0
            return cmd

        cost = state.cost.current if state.cost is not None else 0
        cost_ok = state.cost is None or state.cost.state == "ok"
        hand = {c.name: c for c in state.operator_cards}
        deployed_names = {d.name for d in state.deployed}
        free = set(state.game_map.deployable_ids()) if state.game_map else set()
        ready_skill = {(s.operator, s.slot + 1)
                       for s in state.skills if s.ready}
        used_cells = set()
        planned_ops = set()

        for a in decision.plan.actions:
            ok, reason = self._check(
                a, cost, cost_ok, hand, deployed_names, free,
                ready_skill, used_cells, planned_ops)
            if ok:
                kept.append(a)
                if a.action == "deploy":
                    cost -= hand[a.operator_id].cost
                    used_cells.add(a.grid_pos)
                    planned_ops.add(a.operator_id)
            else:
                dropped.append("%s 动作被快通道拦截：%s" % (a.action, reason))

        note = "快通道：保留 %d 个、拦截 %d 个即时不可执行动作" % (
            len(kept), len(dropped))
        had_kept = bool(kept)
        if not kept:
            kept = [Action(action="wait", duration_ms=500)]
            note += "；全部不可执行，退化为短等待 500ms"
        # 桥接战略意图作为旁路说明（真实路径为隐状态，mock 用文字）
        if bridge is not None and bridge.hint:
            note += " | " + bridge.hint

        # 读数存疑或慢思考动作被全部拦截时，置信度都应下调
        conf = min(decision.confidence, 0.9 if cost_ok else 0.4)
        if not had_kept:
            conf = min(conf, 0.35)
        cmd = FastCommand(
            decision_id=decision.decision_id,
            plan=ActionPlan(actions=kept, reason=decision.plan.reason),
            dropped=dropped, confidence=conf, reactor="mock", note=note)
        cmd.react_ms = (time.time() - start) * 1000.0
        return cmd

    @staticmethod
    def _check(a, cost, cost_ok, hand, deployed_names, free,
               ready_skill, used_cells, planned_ops):
        # type: (...) -> Tuple[bool, str]
        if a.action == "deploy":
            card = hand.get(a.operator_id)
            if card is None:
                return False, "干员 %r 不在当前手牌" % a.operator_id
            if a.operator_id in deployed_names or a.operator_id in planned_ops:
                return False, "干员 %r 已上场或已在本批部署中" % a.operator_id
            if a.grid_pos in used_cells:
                return False, "格子 %s 已被本批前一个部署占用" % a.grid_pos
            if a.grid_pos not in free:
                return False, "格子 %s 当前不可部署/已占用" % a.grid_pos
            if not cost_ok:
                return False, "费用读数存疑，暂不部署"
            if card.cost > cost:
                return False, "费用不足（需要 %d，当前约 %d）" % (card.cost, cost)
            return True, ""
        if a.action == "skill":
            if a.operator_id not in deployed_names:
                return False, "干员 %r 未上场，无法开技能" % a.operator_id
            if (a.operator_id, a.skill_id) not in ready_skill:
                return False, "干员 %r 的技能 %d 当前未就绪" % (
                    a.operator_id, a.skill_id)
            return True, ""
        if a.action == "retreat":
            if a.operator_id not in deployed_names:
                return False, "干员 %r 不在场上，无法撤退" % a.operator_id
            return True, ""
        if a.action == "wait":
            return True, ""
        return False, "未知动作 %r" % a.action
