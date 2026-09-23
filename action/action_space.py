# 纯 CPU、无重依赖：动作空间 Pydantic 契约 + 格子/卡槽坐标转换。
# 与第五批 LLM Agent 的输出 schema（output_schema.py）对齐：决策输出的 action 字段
# 应能直接构造成这里的 Action / ActionPlan。
"""动作空间定义。

四类原子动作（action 字段判别）：
- deploy  部署：operator_id + grid_pos(格子名) + direction
- skill   技能：operator_id + skill_id(槽位 1-3)
- retreat 撤退：operator_id
- wait    等待：duration_ms

Action 用 model_validator 按类型校验"该有的字段必须有、不该有的不能乱填"，
非法组合给出明确中文报错。ActionPlan 支持一次决策输出多个动作批量执行。

坐标转换（全部读 configs，不硬编码）：
- grid_pos('A3') -> 屏幕像素：coords.grid.origin + 列/行步进（等距投影真机阶段校准）；
- 卡槽 slot -> 像素：coords.operator_card_bar 按 cards.count 等分。
"""

import re
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from .config import DEFAULT_CONFIG_PATH, load_action_config

__all__ = ["ActionType", "Direction", "Action", "ActionPlan",
           "ActionResult", "PlanResult", "GridConverter"]

ActionType = Literal["deploy", "skill", "retreat", "wait"]
Direction = Literal["up", "down", "left", "right"]

_CELL_RE = re.compile(r"^([A-Z]{1,2})([0-9]+)$")
_MAX_WAIT_MS = 60000

_DIRECTION_UNIT = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


class Action(BaseModel):
    """单个原子动作。按 action 类型做字段联合校验。"""
    action: ActionType
    operator_id: Optional[str] = Field(None, description="干员标识（卡牌名/已部署干员名）")
    grid_pos: Optional[str] = Field(None, description="目标格子，如 'A3'")
    direction: Direction = "up"
    skill_id: Optional[int] = Field(None, description="技能槽位 1-3")
    duration_ms: Optional[int] = Field(None, description="wait 等待毫秒")

    @model_validator(mode="after")
    def _check_by_type(self):
        if self.action == "deploy":
            if not (self.operator_id or "").strip():
                raise ValueError("deploy 动作缺少 operator_id")
            if not self._valid_cell_format(self.grid_pos):
                raise ValueError("deploy 动作的 grid_pos 非法：%r（应为字母列+数字行，如 A3）"
                                 % self.grid_pos)
            if self.skill_id is not None:
                raise ValueError("deploy 动作不应带 skill_id")
            if self.duration_ms is not None:
                raise ValueError("deploy 动作不应带 duration_ms")
        elif self.action == "skill":
            if not (self.operator_id or "").strip():
                raise ValueError("skill 动作缺少 operator_id")
            if self.skill_id is None:
                raise ValueError("skill 动作缺少 skill_id")
            if not 1 <= self.skill_id <= 3:
                raise ValueError("skill_id 必须在 1-3，收到 %r" % self.skill_id)
            if self.grid_pos is not None:
                raise ValueError("skill 动作不应带 grid_pos")
            if self.duration_ms is not None:
                raise ValueError("skill 动作不应带 duration_ms")
        elif self.action == "retreat":
            if not (self.operator_id or "").strip():
                raise ValueError("retreat 动作缺少 operator_id")
            if self.grid_pos is not None or self.skill_id is not None:
                raise ValueError("retreat 动作只允许 operator_id")
            if self.duration_ms is not None:
                raise ValueError("retreat 动作不应带 duration_ms")
        elif self.action == "wait":
            if self.duration_ms is None:
                raise ValueError("wait 动作缺少 duration_ms")
            if not 0 <= self.duration_ms <= _MAX_WAIT_MS:
                raise ValueError("duration_ms 必须在 0-%d，收到 %r"
                                 % (_MAX_WAIT_MS, self.duration_ms))
            if self.operator_id or self.grid_pos or self.skill_id is not None:
                raise ValueError("wait 动作只允许 duration_ms")
        return self

    @staticmethod
    def _valid_cell_format(cell):
        return bool(cell) and bool(_CELL_RE.match(str(cell).strip().upper()))


class ActionPlan(BaseModel):
    """一次决策可能输出的有序动作序列。"""
    actions: List[Action] = Field(default_factory=list)
    reason: str = ""          # 可携带决策说明（与 Agent reasoning 对齐，执行器忽略）

    def __len__(self):
        return len(self.actions)


class ActionResult(BaseModel):
    """单个动作的执行结果（含其编译出的底层原语日志）。"""
    index: int
    action: str
    success: bool = False
    status: str = "ok"        # ok / failed / timeout / offline / error
    error: str = ""
    ops: List[str] = Field(default_factory=list)   # 实际下发的原语 op 名序列


class PlanResult(BaseModel):
    """整段动作序列执行结果。"""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    completed: bool = False   # 是否把序列走完（失败也继续 => 通常为 True）
    results: List[ActionResult] = Field(default_factory=list)

    @property
    def all_success(self):
        return self.failed == 0 and self.total > 0


def parse_cell(cell_id):
    # type: (str) -> Tuple[int, int]
    """'A3' -> (0,2)；支持双字母 'AA1' -> (26,0)。非法格式抛 ValueError。"""
    m = _CELL_RE.match(str(cell_id).strip().upper())
    if not m:
        raise ValueError("非法格子名：%r（应为字母列+数字行，如 A3）" % cell_id)
    letters, digits = m.group(1), m.group(2)
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    col -= 1
    row = int(digits) - 1
    return col, row


class GridConverter(object):
    """格子名/卡槽位 <-> 屏幕像素，坐标全部来自配置。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_action_config(config_path)
        grid = cfg["coords"]["grid"]
        self.origin = tuple(grid.get("origin", [0, 0]))
        self.cell_step = tuple(grid.get("cell", [0, 0]))
        self.cols = int(grid.get("cols", 10))
        self.rows = int(grid.get("rows", 10))
        bar = cfg["coords"].get("operator_card_bar", [0, 0, 0, 0])
        self.card_bar = tuple(bar)
        self.card_count = int(cfg.get("cards", {}).get("count", 12))
        self.direction_px = int(cfg.get("deploy", {}).get("direction_swipe_px", 60))
        self.retreat_offset = tuple(cfg.get("retreat", {}).get("button_offset", [0, 120]))

    def grid_to_pixel(self, cell_id):
        # type: (str) -> Tuple[int, int]
        col, row = parse_cell(cell_id)
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            raise ValueError("格子 %s 越界：地图为 %d列x%d行（%s 从 0 计）"
                             % (cell_id, self.cols, self.rows, cell_id))
        # TODO 真机校准：等距地图还需按行做斜切偏移；当前用正交步进（占位坐标，仅打通链路）
        x = self.origin[0] + col * self.cell_step[0]
        y = self.origin[1] + row * self.cell_step[1]
        return int(round(x)), int(round(y))

    def card_slot_center(self, slot):
        # type: (int) -> Tuple[int, int]
        if not 0 <= slot < self.card_count:
            raise ValueError("卡槽位 %r 越界：应为 0-%d" % (slot, self.card_count - 1))
        x1, y1, x2, y2 = self.card_bar
        w = max(1, x2 - x1)
        cx = x1 + int(w * (slot + 0.5) / self.card_count)
        cy = (y1 + y2) // 2
        return cx, cy

    def direction_end(self, x, y, direction):
        # type: (int, int, str) -> Tuple[int, int]
        dx, dy = _DIRECTION_UNIT[direction]
        return x + dx * self.direction_px, y + dy * self.direction_px

    def retreat_button(self, x, y):
        # type: (int, int) -> Tuple[int, int]
        return x + self.retreat_offset[0], y + self.retreat_offset[1]
