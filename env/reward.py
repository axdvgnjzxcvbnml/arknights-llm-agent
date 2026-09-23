# 纯 CPU、无重依赖：对局奖励评估。**仅用于评估 Agent 表现，不产生梯度、不用于 RL 训练。**
"""评估用奖励（Evaluation Reward，非 RL）。

逐帧喂状态累计，结束时汇总：
- 通关：+100（win_bonus）
- 漏怪：目标耐久每掉 1 点 -10（leak_penalty，按 life 差值计，与帧频无关）
- 费用溢出：费用打满上限并持续，每秒 -1（overcost_per_sec，按真实 dt 累计）

输出 RewardBreakdown：各项分值、总分、起止耐久、溢出秒数与逐条明细，便于复盘。
所有数值/权重从 RewardConfig 注入，不硬编码。state 仅鸭子类型读取
(state.life_points / state.cost.current / state.cost.limit)，不依赖 perception 包。
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

__all__ = ["RewardConfig", "RewardItem", "RewardBreakdown", "EpisodeReward"]

Outcome = Literal["win", "defeat", "timeout", "aborted"]


class RewardConfig(BaseModel):
    win_bonus: float = 100.0          # 通关
    leak_penalty: float = 10.0       # 每漏 1 点目标耐久
    overcost_per_sec: float = 1.0    # 费用满溢每秒扣分


class RewardItem(BaseModel):
    name: str
    delta: float
    why: str = ""


class RewardBreakdown(BaseModel):
    outcome: str = "aborted"
    win_bonus: float = 0.0
    leak_penalty: float = 0.0
    overcost_penalty: float = 0.0
    total: float = 0.0
    life_start: Optional[int] = None
    life_end: Optional[int] = None
    leaked: int = 0
    overcost_sec: float = 0.0
    items: List[RewardItem] = Field(default_factory=list)

    def summary_line(self):
        return ("总分 %.0f = 通关%+.0f + 漏怪%+.0f(%d点) + 费用溢出%+.0f(%.1fs)"
                % (self.total, self.win_bonus, self.leak_penalty, self.leaked,
                   self.overcost_penalty, self.overcost_sec))


class EpisodeReward(object):
    """一局奖励累加器。用法：reset() -> 每步 observe(state, dt) -> finalize(outcome)。"""

    def __init__(self, config=None):
        self.config = config or RewardConfig()
        self.items = []  # type: List[RewardItem]
        self.life_start = None
        self._last_life = None
        self.overcost_sec = 0.0
        self.leak_points = 0
        self._last_cost = None
        self._cost_limit = None

    def reset(self, initial_life=None, cost_limit=None):
        # type: (Optional[int], Optional[int]) -> EpisodeReward
        self.items = []
        self.life_start = initial_life
        self._last_life = initial_life
        self.overcost_sec = 0.0
        self.leak_points = 0
        self._last_cost = None
        self._cost_limit = cost_limit
        return self

    def observe(self, state, dt_sec=0.0):
        # type: (object, float) -> List[RewardItem]
        """喂入执行动作后的新状态与该步耗时（秒），返回本步新增的扣分项。"""
        new_items = []

        # 目标耐久（漏怪）
        life = getattr(state, "life_points", None)
        if life is not None:
            if self.life_start is None:
                self.life_start = life
            if self._last_life is not None and life < self._last_life:
                drop = int(self._last_life - life)
                self.leak_points += drop
                delta = -self.config.leak_penalty * drop
                item = RewardItem(name="leak", delta=delta,
                                  why="目标耐久 %d->%d，漏怪 %d 点"
                                      % (self._last_life, life, drop))
                self.items.append(item)
                new_items.append(item)
            self._last_life = life

        # 费用溢出（费用达到上限并持续）
        cost_obj = getattr(state, "cost", None)
        if cost_obj is not None and dt_sec and dt_sec > 0:
            current = getattr(cost_obj, "current", None)
            limit = self._cost_limit
            if limit is None:
                limit = getattr(cost_obj, "limit", None)
            if current is not None and limit is not None and current >= limit:
                self.overcost_sec += dt_sec
                delta = -self.config.overcost_per_sec * dt_sec
                item = RewardItem(name="overcost", delta=round(delta, 3),
                                  why="费用 %d 打满上限 %s，溢出 %.1fs"
                                      % (current, limit, dt_sec))
                self.items.append(item)
                new_items.append(item)
            self._last_cost = current
        return new_items

    def finalize(self, outcome):
        # type: (str) -> RewardBreakdown
        win_bonus = self.config.win_bonus if outcome == "win" else 0.0
        if win_bonus:
            self.items.append(RewardItem(
                name="win", delta=win_bonus, why="通关成功"))
        leak_penalty = -self.config.leak_penalty * self.leak_points
        overcost_penalty = -self.config.overcost_per_sec * self.overcost_sec
        total = win_bonus + leak_penalty + overcost_penalty
        if outcome not in ("win", "defeat", "timeout", "aborted"):
            outcome = "aborted"
        return RewardBreakdown(
            outcome=outcome,
            win_bonus=win_bonus,
            leak_penalty=round(leak_penalty, 3),
            overcost_penalty=round(overcost_penalty, 3),
            total=round(total, 3),
            life_start=self.life_start,
            life_end=self._last_life,
            leaked=self.leak_points,
            overcost_sec=round(self.overcost_sec, 3),
            items=list(self.items))
