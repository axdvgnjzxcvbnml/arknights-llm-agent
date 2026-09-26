# TODO-V100: 快反应真实推理需要 V100（MiniCPM 级小模型，单步目标 <150ms）。
# CPU 沙箱不加载模型；真实 react raise NotImplementedError。import 不拉起 transformers。
"""快反应模型：慢思考战略意图（BridgeState）+ 当前屏幕状态 -> 可立即执行的 FastCommand。

与慢思考的分工：慢思考负责"打哪、为什么"（秒级、可解释），快反应负责"这一拍能不能做、
先做哪个"（毫秒级）。它会用**当前帧**对慢思考给出的动作做即时可行性裁剪：
费用不够 / 干员不在手牌 / 格子被占或不可部署 / 技能未就绪的动作被丢弃并写明原因，
全部不可执行时退化为一个短 wait，绝不下达乱点的指令。

增强规则（第二十二批）：
- 部署优先级排序：先锋/近卫（阻挡）> 狙击/术师/重装（输出）> 医疗/辅助（辅助）
- 干员朝向校验：direction 必须合法（left/right/up/down），远程建议朝敌
- 技能时机判断：场上无敌人时不开技能（避免空放）
- cost.state == "missing"：保留上一稳定费用值，不拦截但标注
- cost.state == "uncertain"：拦截部署，不拦截技能/撤退
- 连续 N 次全部动作被拦截：标记"建议触发慢思考"，置信度下调

- FastReactorMiniCPM：V100 真实实现（TODO-V100）；
- MockFastReactor：纯 CPU 规则裁剪，确定性，用于全链路联调。
"""

import time
from typing import List, Optional, Tuple

from action.action_space import Action, ActionPlan

from .config import DEFAULT_CONFIG_PATH, load_agent_config
from .output_schema import AgentDecision, BridgeState, FastCommand

__all__ = ["BaseFastReactor", "FastReactorMiniCPM", "MockFastReactor"]

# 部署优先级（占位规则，inferred:placeholder）
# 注意：此排序是凭经验拍脑袋的占位值，未经过 MAA 作业数据统计验证。
# 正确做法：从 data/sft_data/sft_all.jsonl 统计各职业在各关卡的部署时序，
# 或用血狼破军强度榜数据校准。TODO: 待数据校准后替换。
_DEPLOY_PRIORITY = {
    "先锋": 0, "近卫": 0, "重装": 1,
    "狙击": 1, "术师": 1,
    "医疗": 2, "辅助": 2, "特种": 2,
}
_DEFAULT_PRIORITY = 1  # 未知职业按输出处理

# 远程职业（需要朝向敌人）
_RANGED_CLASSES = ("狙击", "术师", "辅助")


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
    """当前帧可行性裁剪（确定性，纯 CPU）。

    增强规则：部署优先级排序、朝向校验、技能时机、cost missing 保留上一稳定值、
    连续 N 次无决策触发慢思考建议。
    """

    reactor_name = "mock"

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        super(MockFastReactor, self).__init__(config, config_path)
        # cost.state == "missing" 时保留上一稳定值
        self._last_stable_cost = None  # type: Optional[int]
        # 连续全部动作被拦截的计数
        self._consecutive_noop = 0
        # 触发慢思考建议的阈值
        fast_cfg = self.config.get("models", {}).get("fast", {})
        self._noop_threshold = int(fast_cfg.get("noop_trigger_slow_threshold", 3))

    def react(self, state, decision, bridge=None):
        start = time.time()
        kept = []          # type: List[Action]
        dropped = []       # type: List[str]
        notes_extra = []   # type: List[str]

        if state is None:
            self._consecutive_noop += 1
            cmd = FastCommand(
                decision_id=decision.decision_id,
                plan=ActionPlan(actions=[Action(action="wait", duration_ms=500)]),
                dropped=["无当前状态，慢思考动作全部挂起，改为短等待"],
                confidence=0.2, reactor="mock",
                note="快通道：状态缺失，保守等待")
            cmd.react_ms = (time.time() - start) * 1000.0
            return cmd

        # ---- 费用状态处理 ----
        cost_state = state.cost.state if state.cost is not None else "ok"
        if cost_state == "ok" and state.cost is not None:
            self._last_stable_cost = state.cost.current
            cost = state.cost.current
        elif cost_state == "missing":
            # 读数缺失：使用上一稳定值
            cost = self._last_stable_cost if self._last_stable_cost is not None else 0
            notes_extra.append("费用读数缺失，使用上一稳定值 %d" % cost)
        else:  # uncertain
            cost = state.cost.current if state.cost is not None else 0

        cost_ok = cost_state == "ok" or cost_state == "missing"
        # uncertain 时部署被拦截，但技能/撤退不拦截

        hand = {c.name: c for c in state.operator_cards}
        deployed_names = {d.name for d in state.deployed}
        free = set(state.game_map.deployable_ids()) if state.game_map else set()
        ready_skill = {(s.operator, s.slot + 1)
                       for s in state.skills if s.ready}
        has_enemies = bool(state.enemies_on_field)
        used_cells = set()
        planned_ops = set()

        for a in decision.plan.actions:
            ok, reason = self._check(
                a, cost, cost_ok, hand, deployed_names, free,
                ready_skill, used_cells, planned_ops, has_enemies)
            if ok:
                kept.append(a)
                if a.action == "deploy":
                    cost -= hand[a.operator_id].cost
                    used_cells.add(a.grid_pos)
                    planned_ops.add(a.operator_id)
            else:
                dropped.append("%s 动作被快通道拦截：%s" % (a.action, reason))

        # ---- 部署优先级排序（inferred:placeholder，待MAA作业数据校准） ----
        deploy_actions = [a for a in kept if a.action == "deploy"]
        other_actions = [a for a in kept if a.action != "deploy"]
        if deploy_actions:
            deploy_actions.sort(key=lambda a: (
                _DEPLOY_PRIORITY.get(hand[a.operator_id].operator_class, _DEFAULT_PRIORITY),
                a.operator_id))
            # 远程干员朝向确认提示
            for a in deploy_actions:
                card = hand.get(a.operator_id)
                if card and card.operator_class in _RANGED_CLASSES:
                    notes_extra.append(
                        "远程干员 %s 朝向 %s，请确认朝向敌人方向" % (a.operator_id, a.direction))
        kept = deploy_actions + other_actions

        note = "快通道：保留 %d 个、拦截 %d 个即时不可执行动作" % (
            len(kept), len(dropped))
        if notes_extra:
            note += " | " + "；".join(notes_extra)
        had_kept = bool(kept)

        # ---- 连续无决策检测 ----
        if not had_kept:
            self._consecutive_noop += 1
            kept = [Action(action="wait", duration_ms=500)]
            note += "；全部不可执行，退化为短等待 500ms"
            if self._consecutive_noop >= self._noop_threshold:
                note += (" | 连续 %d 次无法决策，建议触发慢思考重新评估"
                         % self._consecutive_noop)
        else:
            self._consecutive_noop = 0

        # 桥接战略意图作为旁路说明（真实路径为隐状态，mock 用文字）
        if bridge is not None and bridge.hint:
            note += " | " + bridge.hint

        # 读数存疑或慢思考动作被全部拦截时，置信度都应下调
        conf = min(decision.confidence, 0.9 if cost_state == "ok" else 0.5)
        if not had_kept:
            conf = min(conf, 0.35)
            if self._consecutive_noop >= self._noop_threshold:
                conf = min(conf, 0.2)
        cmd = FastCommand(
            decision_id=decision.decision_id,
            plan=ActionPlan(actions=kept, reason=decision.plan.reason),
            dropped=dropped, confidence=conf, reactor="mock", note=note)
        cmd.react_ms = (time.time() - start) * 1000.0
        return cmd

    @staticmethod
    def _check(a, cost, cost_ok, hand, deployed_names, free,
               ready_skill, used_cells, planned_ops, has_enemies=True):
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
            # 技能时机：场上无敌人时不开技能（避免空放）
            if not has_enemies:
                return False, "场上无敌人，暂不开技能（避免空放）"
            return True, ""
        if a.action == "retreat":
            if a.operator_id not in deployed_names:
                return False, "干员 %r 不在场上，无法撤退" % a.operator_id
            return True, ""
        if a.action == "wait":
            return True, ""
        return False, "未知动作 %r" % a.action
