# 环境封装：把"看 -> 想/外部给动作 -> 做 -> 再看"封装成统一接口。
# 纯调度，**不产生梯度、不用于 RL 训练**；真实模拟器与 mock 走同一接口，V100 上线只换注入组件。
# import 本模块只依赖 pydantic 与 action（均无 numpy/torch），perception/agent 由调用方注入。
"""Gym 风格环境（注意：是调度接口，不是 RL 训练环境）。

依赖注入三大块（构造函数传入，mock/真实可互换）：
- perception：至少提供 perceive(elapsed_sec) -> {frame,state,analysis,state_text}、
  on_after_step(plan, plan_result)；可提供 regen()、is_cleared()；
- executor：execute(ActionPlan) -> PlanResult（action 包）；
- 可选 Agent 组件 knowledge/slow/bridge/fast：提供后可用 run_episode() 自动跑完整一局。

API（Gym 风格）：
    reset() -> GameState
    step(action) -> (next_state, step_reward, done, info)
    get_state() / is_done() / get_log()

每一步记录 EnvStep（状态文本、动作、执行结果、决策理由、证据、奖励、耗时），
结束由 EpisodeReward 汇总为 RewardBreakdown，整体构成 EpisodeLog 对局日志。
"""

import time
from typing import List, Optional

from pydantic import BaseModel, Field

from action.action_space import Action, ActionPlan, PlanResult

from .reward import EpisodeReward, RewardConfig, RewardItem

__all__ = ["EnvStep", "EpisodeLog", "ArknightsEnv", "coerce_plan",
           "render_episode_report"]


def coerce_plan(action):
    # type: (object) -> ActionPlan
    """把 Action / ActionPlan / FastCommand / List[Action] 统一成 ActionPlan。"""
    if isinstance(action, ActionPlan):
        return action
    if isinstance(action, Action):
        return ActionPlan(actions=[action])
    if isinstance(action, list):
        return ActionPlan(actions=list(action))
    plan = getattr(action, "plan", None)   # FastCommand
    if isinstance(plan, ActionPlan):
        return plan
    raise TypeError("无法把 %r 转为 ActionPlan" % type(action).__name__)


class EnvStep(BaseModel):
    """一步对局记录（可解释对局报告的基本单元）。"""
    step: int
    elapsed_sec: float
    state_text: str = ""
    cost: Optional[int] = None
    life: Optional[int] = None
    plan: ActionPlan = Field(default_factory=ActionPlan)
    plan_result: Optional[PlanResult] = None
    decision_summary: str = ""
    decision_analysis: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)   # "level:source"
    reward_items: List[RewardItem] = Field(default_factory=list)
    step_reward: float = 0.0
    latency_ms: dict = Field(default_factory=dict)


class EpisodeLog(BaseModel):
    stage_id: str = ""
    outcome: str = "aborted"             # win / defeat / timeout / aborted
    steps: List[EnvStep] = Field(default_factory=list)
    reward: Optional[object] = None      # RewardBreakdown（避免跨包强类型耦合）
    duration_sec: float = 0.0
    backend: str = "mock"

    @property
    def total_reward(self):
        return getattr(self.reward, "total", 0.0)


class ArknightsEnv(object):
    def __init__(self, perception, executor, knowledge=None, slow=None,
                 bridge=None, fast=None, config=None, reward_config=None,
                 stage_id="3-8", step_dt_sec=None, max_steps=None,
                 backend="mock"):
        self.perception = perception
        self.executor = executor
        self.knowledge = knowledge
        self.slow = slow
        self.bridge = bridge
        self.fast = fast
        self.backend = backend

        if config is None:
            try:
                from agent.config import load_agent_config
                config = load_agent_config()
            except Exception:
                config = {}
        self.config = config
        loop_cfg = (config or {}).get("loop", {}) if isinstance(config, dict) else {}
        self.max_steps = int(max_steps if max_steps is not None
                             else loop_cfg.get("max_steps", 10))
        # 每步代表的对局秒数（用于费用溢出计时）；mock 默认 1s
        self.step_dt_sec = float(step_dt_sec if step_dt_sec is not None
                                 else loop_cfg.get("step_dt_sec", 1.0))

        self.stage_id = stage_id
        self.reward_tracker = EpisodeReward(reward_config or RewardConfig())

        self._state = None
        self._frame = None
        self._pf = None
        self.elapsed_sec = 0.0
        self.tick = 0
        self.steps = []           # type: List[EnvStep]
        self.outcome = None
        self._start_wall = 0.0
        self._breakdown = None

    # ---------------- Gym 风格 API ----------------
    def reset(self, stage_id=None):
        self.stage_id = stage_id or self.stage_id
        self.elapsed_sec = 0.0
        self.tick = 0
        self.steps = []
        self.outcome = None
        self._breakdown = None
        self._start_wall = time.time()
        self.reward_tracker = EpisodeReward(self.reward_tracker.config)

        self._pf = self.perception.perceive(0.0)
        self._state = self._pf.state
        cost_limit = self._state.cost.limit if getattr(self._state, "cost", None) else None
        self.reward_tracker.reset(self._state.life_points, cost_limit)
        return self._state

    def step(self, action, decision=None, knowledge=None):
        # type: (object, object, object) -> tuple
        """执行一动作（或一段 ActionPlan），再感知新状态。返回 (state,reward,done,info)。"""
        if self._state is None:
            raise RuntimeError("请先调用 reset() 再 step()")
        plan = coerce_plan(action)

        t0 = time.time()
        plan_result = self.executor.execute(plan)
        exec_ms = (time.time() - t0) * 1000.0

        # 让感知层用真实执行结果更新战局（部署成功才离手牌/占格）
        if hasattr(self.perception, "on_after_step"):
            self.perception.on_after_step(plan, plan_result)

        self.tick += 1
        self.elapsed_sec += self.step_dt_sec
        if hasattr(self.perception, "regen"):
            self.perception.regen()

        self._pf = self.perception.perceive(self.elapsed_sec)
        self._state = self._pf.state
        reward_items = self.reward_tracker.observe(self._state, self.step_dt_sec)
        step_reward = round(sum(i.delta for i in reward_items), 3)

        done, outcome = self._check_done()
        if done:
            self.outcome = outcome
            self._breakdown = self.reward_tracker.finalize(outcome)

        latency = {"execute_ms": round(exec_ms, 1)}
        if decision is not None and hasattr(decision, "thought_ms"):
            latency["slow_ms"] = round(decision.thought_ms, 1)
        summary, analysis, evidence = _decision_brief(decision, knowledge)

        cost = self._state.cost.current if getattr(self._state, "cost", None) else None
        record = EnvStep(
            step=self.tick, elapsed_sec=self.elapsed_sec,
            state_text=getattr(self._pf, "state_text", ""),
            cost=cost, life=self._state.life_points,
            plan=plan, plan_result=plan_result,
            decision_summary=summary, decision_analysis=analysis,
            evidence=evidence, reward_items=reward_items,
            step_reward=step_reward, latency_ms=latency)
        self.steps.append(record)

        info = {"outcome": self.outcome, "tick": self.tick,
                "succeeded": plan_result.succeeded, "failed": plan_result.failed}
        return self._state, step_reward, done, info

    def get_state(self):
        return self._state

    def is_done(self):
        return self.outcome is not None

    def get_log(self):
        # type: () -> EpisodeLog
        breakdown = self._breakdown
        if breakdown is None:
            # 未正常结束也给一份临时汇总（aborted），便于随时查看
            breakdown = self.reward_tracker.finalize(self.outcome or "aborted")
        return EpisodeLog(
            stage_id=self.stage_id, outcome=self.outcome or "aborted",
            steps=list(self.steps), reward=breakdown,
            duration_sec=round(time.time() - self._start_wall, 3),
            backend=self.backend)

    def close(self, outcome="aborted"):
        """外部提前终止一局。"""
        self.outcome = outcome
        self._breakdown = self.reward_tracker.finalize(outcome)
        return self.get_log()

    # ---------------- 自动对局（注入 Agent 组件时）----------------
    def run_episode(self, stage_id=None, max_steps=None):
        # type: (Optional[str], Optional[int]) -> EpisodeLog
        missing = [n for n, v in (("knowledge", self.knowledge), ("slow", self.slow),
                                  ("bridge", self.bridge), ("fast", self.fast))
                   if v is None]
        if missing:
            raise RuntimeError("run_episode 需要注入 Agent 组件，缺少：%s" % ", ".join(missing))
        limit = int(max_steps if max_steps is not None else self.max_steps)
        self.reset(stage_id)
        done = False
        while not done and self.tick < limit:
            knowledge = self.knowledge.gather(self._state)
            t0 = time.time()
            decision = self.slow.think(
                stage_id=self.stage_id, elapsed_sec=self.elapsed_sec,
                state_text=self._pf.state_text, knowledge=knowledge,
                state=self._state)
            bridge_state = self.bridge.project(decision)
            command = self.fast.react(self._state, decision, bridge_state)
            think_ms = (time.time() - t0) * 1000.0
            _state, _r, done, _info = self.step(command, decision=decision,
                                                knowledge=knowledge)
            self.steps[-1].latency_ms["agent_ms"] = round(think_ms, 1)
        if not done:
            # 到达步数上限仍未判负/通关：记 timeout 并结算
            self.outcome = "timeout"
            self._breakdown = self.reward_tracker.finalize("timeout")
        return self.get_log()

    # ---------------- 结束判定 ----------------
    def _check_done(self):
        life = getattr(self._state, "life_points", None)
        if life is not None and life <= 0:
            return True, "defeat"
        clearer = getattr(self.perception, "is_cleared", None)
        if callable(clearer) and clearer():
            return True, "win"
        if self.tick >= self.max_steps:
            return True, "timeout"
        return False, None


def _decision_brief(decision, knowledge):
    """从 AgentDecision/None 提取 (结论, 依据列表, 证据标注列表)，鸭子类型不跨包强依赖。"""
    if decision is None:
        return "", [], []
    reasoning = getattr(decision, "reasoning", None)
    summary = getattr(reasoning, "summary", "") if reasoning is not None else ""
    analysis = list(getattr(reasoning, "analysis", []) or []) if reasoning is not None else []
    citations = getattr(decision, "knowledge_used", None)
    if not citations and knowledge is not None:
        citations = getattr(knowledge, "citations", [])
    evidence = []
    for c in (citations or []):
        evidence.append("%s:%s" % (getattr(c, "evidence", "?"), getattr(c, "source", "?")))
    return summary, analysis, evidence


_OUTCOME_CN = {"win": "通关", "defeat": "失败（生命归零）",
               "timeout": "到达步数上限", "aborted": "中止"}


def render_episode_report(log):
    # type: (EpisodeLog) -> str
    """把一局 EpisodeLog 渲染成可读对局报告（每步状态/动作/理由/耗时/奖励）。"""
    L = []
    L.append("# arknights-llm-agent 对局报告")
    L.append("关卡=%s backend=%s 结果=%s 步数=%d 墙钟=%.3fs" % (
        log.stage_id, log.backend, _OUTCOME_CN.get(log.outcome, log.outcome),
        len(log.steps), log.duration_sec))
    if getattr(log.reward, "summary_line", None):
        L.append("奖励：" + log.reward.summary_line())

    for st in log.steps:
        L.append("")
        L.append("=" * 68)
        L.append("步 %d | 对局 t=%.0fs | 费用=%s 耐久=%s | 耗时 %s" % (
            st.step, st.elapsed_sec,
            st.cost if st.cost is not None else "?",
            st.life if st.life is not None else "?",
            " ".join("%s=%.0fms" % (k, v) for k, v in st.latency_ms.items())))
        if st.decision_summary:
            L.append("决策: " + st.decision_summary)
        for i, a in enumerate(st.decision_analysis, 1):
            L.append("  依据%d: %s" % (i, a))
        if st.evidence:
            L.append("  证据: " + "；".join(st.evidence))
        if st.plan_result is not None:
            for ar in st.plan_result.results:
                L.append("  动作 #%d %-7s %s %s" % (
                    ar.index, ar.action, "成功" if ar.success else "失败(" + ar.status + ")",
                    "->".join(ar.ops) if ar.success else ar.error))
        if st.reward_items:
            L.append("  本步奖励: %+.1f（%s）" % (
                st.step_reward, "；".join("%s%+.1f" % (i.name, i.delta)
                                         for i in st.reward_items)))

    if log.reward is not None and getattr(log.reward, "items", None):
        L.append("")
        L.append("-- 奖励明细 --")
        for it in log.reward.items:
            L.append("  %-8s %+.1f  %s" % (it.name, it.delta, it.why))
        L.append("总分: %s" % getattr(log.reward, "total", 0.0))
    return "\n".join(L)
