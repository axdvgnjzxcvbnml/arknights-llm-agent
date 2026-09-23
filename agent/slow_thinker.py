# TODO-V100: 慢思考真实推理需要 V100（Qwen/Qwen3-8B-Thinking，bf16）。
# CPU 沙箱不加载模型；SlowThinkerQwen3 的模型加载与生成均 raise NotImplementedError。
# 本文件 import 不拉起 torch/transformers（真实依赖在方法内延迟导入）。
"""慢思考模型：游戏状态 + RAG + 知识图谱 -> 结构化 AgentDecision。

- SlowThinkerQwen3：V100 真实实现（TODO-V100），负责强推理与可读思维链；
- MockSlowThinker：纯 CPU、确定性、**状态感知**的规则决策，用于全链路联调与冒烟；
  它不是每次返回固定动作，而是根据费用/手牌/已部署/敌情/空格子做合理选择，
  其余交给 fast_reactor 做即时可行性裁剪。

Prompt 模板在 prompt_templates/（system/decision/reasoning/self_reflect），用 {{TOKEN}}
占位、整串替换（不用 str.format，避免 JSON 花括号冲突）。
"""

import os
import time
from typing import Dict, List, Optional

from action.action_space import Action, ActionPlan

from .config import DEFAULT_CONFIG_PATH, load_agent_config
from .output_schema import (AgentDecision, KnowledgeBundle, Reflection, Reasoning)

__all__ = ["load_template", "render_template", "BaseSlowThinker",
           "SlowThinkerQwen3", "MockSlowThinker"]

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "prompt_templates")

# 职业 -> 简中（mock 手牌职业名匹配用）
_VANGUARD = ("先锋",)
_SNIPER = ("狙击",)
_CASTER = ("术师", "术师", "法师")
_MEDIC = ("医疗",)


def load_template(name, template_dir=None):
    # type: (str, Optional[str]) -> str
    path = os.path.join(template_dir or _TEMPLATE_DIR, name)
    if not path.endswith(".md"):
        path += ".md"
    if not os.path.exists(path):
        raise FileNotFoundError("Prompt 模板不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_template(template, mapping):
    # type: (str, Dict[str, str]) -> str
    out = template
    for key, val in mapping.items():
        out = out.replace("{{%s}}" % key, str(val))
    return out


class BaseSlowThinker(object):
    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        self.config = config or load_agent_config(config_path)
        tdir = self.config.get("prompt", {}).get("template_dir", "")
        self.template_dir = tdir if (tdir and os.path.isdir(tdir)) else _TEMPLATE_DIR
        self.think_budget_ms = int(
            self.config["models"]["slow"].get("think_budget_ms", 4000))

    def think(self, stage_id, elapsed_sec, state_text, knowledge,
              reflection=None, state=None):
        # type: (...) -> AgentDecision
        raise NotImplementedError

    def reflect(self, decision, plan_result, new_state_text=""):
        # type: (AgentDecision, object, str) -> Reflection
        raise NotImplementedError

    # 真实模型共用的 prompt 组装（V100 上 _generate 直接用）
    def build_prompt(self, state_text, knowledge, reflection=None,
                     available_operators="", deployable_grids="", cost=""):
        # type: (str, KnowledgeBundle, Optional[Reflection], str, str, str) -> List[dict]
        system = load_template("system", self.template_dir)
        decision_tpl = load_template("decision", self.template_dir)
        reasoning_tpl = load_template("reasoning", self.template_dir)
        user = render_template(decision_tpl, {
            "STATE": state_text,
            "AVAILABLE_OPERATORS": available_operators or "（无）",
            "DEPLOYABLE_GRIDS": deployable_grids or "（无空格）",
            "COST": cost or "未知",
            "KNOWLEDGE": knowledge.context_text or "（本轮未检索到知识）",
            "REFLECTION": reflection.adjustment if reflection else "（无上一步反思）",
        })
        user += "\n\n" + render_template(reasoning_tpl,
                                         {"THINK_BUDGET_MS": self.think_budget_ms})
        return [{"role": "system", "content": system},
                {"role": "user", "content": user}]


class SlowThinkerQwen3(BaseSlowThinker):
    """V100 慢思考真实实现。CPU 沙箱不可用。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        super(SlowThinkerQwen3, self).__init__(config, config_path)
        self.model_name = self.config["models"]["slow"]["name"]
        self.device = self.config["models"]["slow"].get("device", "cuda:0")
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        # TODO-V100: 在 V100 上加载 Qwen3-8B-Thinking（transformers + accelerate，bf16），
        # 并启用 thinking/思维链；CPU 沙箱无 GPU、不下载权重，这里不执行真实加载。
        raise NotImplementedError(
            "TODO-V100: 慢思考模型 %s 需在 V100 上加载（device=%s, bf16）；"
            "CPU 侧请使用 backend=mock / MockSlowThinker。"
            % (self.model_name, self.device))

    def think(self, stage_id, elapsed_sec, state_text, knowledge,
              reflection=None, state=None):
        if self._model is None:
            self._load_model()
        # TODO-V100: 用 build_prompt(...) 组装消息 -> chat 生成 -> 解析 JSON 为
        # AgentDecision（含 reasoning/plan/confidence/knowledge_used），并做越界校验。
        raise NotImplementedError(
            "TODO-V100: Qwen3-8B-Thinking 生成与结构化解析在 V100 上实现。")

    def reflect(self, decision, plan_result, new_state_text=""):
        # TODO-V100: 用 self_reflect.md 模板让模型产出 Reflection。
        raise NotImplementedError("TODO-V100: 慢思考反思在 V100 上实现。")


class MockSlowThinker(BaseSlowThinker):
    """确定性、状态感知的 mock 慢思考（纯 CPU）。"""

    thinker_name = "mock"

    def think(self, stage_id, elapsed_sec, state_text, knowledge,
              reflection=None, state=None):
        start = time.time()
        if state is None:
            # 没有结构化状态时保守等待（空状态安全）
            decision = self._wait_decision(
                stage_id, elapsed_sec, knowledge,
                summary="缺少结构化状态，保守等待观察。",
                risks=["视觉状态缺失"])
            decision.thought_ms = (time.time() - start) * 1000.0
            return decision

        cost = state.cost.current if state.cost is not None else 0
        free = state.game_map.deployable_ids() if state.game_map else []
        deployed_names = {d.name for d in state.deployed}
        # 只在"仍在手牌、费用够、尚未上场"的干员里选；已上场的干员由感知从手牌移除，
        # 因此无需从 DeployedOperator（无职业字段）反查职业，也不会重复部署同一干员。
        cards = [c for c in state.operator_cards
                 if c.available and c.cost <= cost and c.name not in deployed_names]

        action = None
        why = ""
        if cards and free:
            pick, grid, direction, why = self._choose(cards, free, state)
            if pick is not None:
                action = Action(action="deploy", operator_id=pick.name,
                                grid_pos=grid, direction=direction)

        if action is None:
            decision = self._wait_decision(
                stage_id, elapsed_sec, knowledge,
                summary=("暂无可部署项（费用不足/无空格/手牌已下），等待回费与敌情明朗。"
                         if not action else "观察"),
                risks=self._state_risks(state))
        else:
            analysis = [
                "当前费用%d，%s（%s,%d费）费用足够。" % (cost, pick.name,
                                                  pick.operator_class, pick.cost),
                "选择格子 %s、朝%s：敌人主要从左侧来，朝左可第一时间接敌。" % (grid, "左"),
                why,
                "已部署 %d 名干员，部署位%s。" % (
                    len(state.deployed),
                    ("/%d" % state.deploy_limit) if state.deploy_limit is not None else "未知"),
            ]
            considered = []
            for c in cards:
                if c.name != pick.name:
                    considered.append("暂不部署 %s（%s）：本步优先『%s』"
                                      % (c.name, c.operator_class, why))
            plan = ActionPlan(actions=[action], reason="mock 慢思考：%s" % why)
            decision = AgentDecision(
                stage_id=stage_id, elapsed_sec=float(elapsed_sec),
                reasoning=Reasoning(summary="部署 %s 到 %s" % (pick.name, grid),
                                    analysis=analysis, considered_actions=considered,
                                    risks=self._state_risks(state)),
                plan=plan, confidence=self._confidence(state),
                knowledge_used=list(knowledge.citations),
                thinker="mock")
        decision.thought_ms = (time.time() - start) * 1000.0
        return decision

    # ---- mock 选牌/选位 ----
    def _choose(self, cards, free, state):
        enemy_names = " ".join(e.name for e in state.enemies_on_field)
        by_class = {}
        for c in cards:
            by_class.setdefault(c.operator_class, c)

        pick = None
        reason = ""
        # 1) 手牌里还有先锋 -> 先下先锋回费（已上场的先锋不在 cards 中，不会重复）
        if any(c.operator_class in _VANGUARD for c in cards):
            pick = by_class.get("先锋")
            reason = "先下先锋尽快回费"
        # 2) 有高防/重装敌人且有术师 -> 上术师（法伤破甲）
        elif ("重装" in enemy_names or "高防" in enemy_names) and any(
                c.operator_class in _CASTER for c in cards):
            pick = next(c for c in cards if c.operator_class in _CASTER)
            reason = "出现重装/高防敌人，术师法伤更有效"
        # 3) 已有两名干员且有医疗 -> 补医疗保线
        elif len(state.deployed) >= 2 and any(c.operator_class in _MEDIC for c in cards):
            pick = by_class.get("医疗")
            reason = "阵线展开后补医疗维持血线"
        # 4) 否则补狙击输出
        elif any(c.operator_class in _SNIPER for c in cards):
            pick = by_class.get("狙击")
            reason = "补狙击提供远程/对空输出"
        # 5) 兜底：最便宜的
        if pick is None and cards:
            pick = sorted(cards, key=lambda c: c.cost)[0]
            reason = "取当前费用可承担的最便宜干员"
        if pick is None:
            return None, "", "up", reason

        # 站位：先锋放前排（第一个空格）；后排职业（狙击/医疗/术师）放靠后空格
        backline = pick.operator_class in _SNIPER + _MEDIC + _CASTER
        grid = free[-1] if (backline and len(free) > 1) else free[0]
        return pick, grid, "left", reason

    @staticmethod
    def _state_risks(state):
        risks = []
        if state.timing_source == "estimated":
            risks.append("敌情出场为均匀估算（estimated），非精确波次")
        if state.cost is not None and state.cost.state != "ok":
            risks.append("费用读数状态为 %s，谨慎决策" % state.cost.state)
        if state.life_points is not None and state.life_points <= 3:
            risks.append("目标耐久仅 %d，需防漏怪" % state.life_points)
        return risks

    def _confidence(self, state):
        conf = 0.7
        if state.timing_source == "estimated":
            conf -= 0.15
        if state.cost is not None and state.cost.state != "ok":
            conf -= 0.1
        return max(0.1, min(0.95, conf))

    def _wait_decision(self, stage_id, elapsed_sec, knowledge, summary, risks):
        return AgentDecision(
            stage_id=stage_id, elapsed_sec=float(elapsed_sec),
            reasoning=Reasoning(
                summary=summary,
                analysis=["本步不下达部署/技能/撤退，等待 1000ms 继续观察。"],
                considered_actions=["部署：当前无费用足够且未上场的干员或无空格"],
                risks=risks),
            plan=ActionPlan(actions=[Action(action="wait", duration_ms=1000)],
                            reason="mock 慢思考：等待观察"),
            confidence=0.45, knowledge_used=list(knowledge.citations),
            thinker="mock")

    def reflect(self, decision, plan_result, new_state_text=""):
        failed = [r for r in (plan_result.results if plan_result else [])
                  if not r.success]
        if not failed:
            return Reflection(decision_id=decision.decision_id, verdict="good",
                              issues=[], adjustment="上一步动作全部成功，按计划继续展开阵线。",
                              confidence=0.7)
        issues = ["#%d %s 失败：%s" % (r.index, r.action, r.error or r.status)
                  for r in failed]
        verdict = "bad" if len(failed) == plan_result.total else "risky"
        return Reflection(
            decision_id=decision.decision_id, verdict=verdict, issues=issues,
            adjustment=("部分动作不可执行，下一步重新核对干员是否在手牌、费用与格子，"
                        "必要时改为等待。"),
            confidence=0.4)
