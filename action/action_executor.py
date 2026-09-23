# 动作执行器：把高层 Action 编译成底层 ADB 原语（tap/swipe/wait）再下发。
# 真机手势与坐标均为占位（configs 坐标待真机校准）；CPU 侧用 Mock 控制器跑通编排与容错。
"""动作执行器。

关键拆分：compile（纯编排，不碰设备）与 execute（经 controller 下发）。
- compile 决定每个高层动作要发哪些 tap/swipe/wait；
- execute 顺序下发，单个动作失败只记录原因、中止该动作，不中断整段序列。

干员定位（operator_id -> 卡槽位 / 已部署格子）由 resolver 提供，resolver 数据来自
当前视觉手牌/已部署状态（perception），不在此臆造：
- card_slot_resolver(operator_id) -> 底部卡槽序号(0 起) 或 None
- deployed_cell_resolver(operator_id) -> 已部署格子名(如 'E4') 或 None
"""

import time
from typing import Callable, List, Optional

from .action_space import (Action, ActionPlan, ActionResult, GridConverter,
                           PlanResult)
from .adb_controller import ADBControllerError, MockADBController, _BaseController
from .config import DEFAULT_CONFIG_PATH, load_action_config

__all__ = ["ActionExecutor", "MockActionExecutor"]

CardSlotResolver = Callable[[str], Optional[int]]
DeployedCellResolver = Callable[[str], Optional[str]]


class ActionExecutor(object):
    def __init__(self, controller, config=None, config_path=DEFAULT_CONFIG_PATH,
                 card_slot_resolver=None, deployed_cell_resolver=None,
                 real_sleep=True):
        self.ctrl = controller
        cfg = config or load_action_config(config_path)
        self.timing = cfg.get("timing", {})
        self.skill_buttons = cfg["coords"].get("skill_buttons", []) or []
        self.grid = GridConverter(cfg)
        self.card_slot_resolver = card_slot_resolver
        self.deployed_cell_resolver = deployed_cell_resolver
        self.real_sleep = real_sleep
        self.action_log = []  # type: List[Action]

    # ---------- 等待 ----------
    def _sleep(self, ms):
        if self.real_sleep and ms and ms > 0:
            time.sleep(ms / 1000.0)

    # ---------- 编译：高层动作 -> 原语步骤 ----------
    def _compile(self, action):
        # type: (Action) -> List[tuple]
        """返回 (kind, kwargs) 步骤列表；无法定位时抛 ValueError（被 execute 捕获）。"""
        steps = []  # type: List[tuple]
        if action.action == "wait":
            steps.append(("wait", {"ms": action.duration_ms}))
            return steps

        if action.action == "deploy":
            slot = self.card_slot_resolver(action.operator_id) \
                if self.card_slot_resolver else None
            if slot is None:
                raise ValueError("未在底部手牌找到干员 %r 的卡槽位（card_slot_resolver 返回空）"
                                 % action.operator_id)
            card_x, card_y = self.grid.card_slot_center(slot)
            gx, gy = self.grid.grid_to_pixel(action.grid_pos)
            ex, ey = self.grid.direction_end(gx, gy, action.direction)
            # 占位手势：点卡牌 -> 停顿 -> 从目标格朝部署方向滑出（确定朝向）。
            # TODO 真机校准：明日方舟为拖放部署，真机需改成"卡牌拖到格子+朝向点选"。
            steps.append(("tap", {"x": card_x, "y": card_y}))
            steps.append(("wait", {"ms": self.timing.get("tap_settle_ms", 80)}))
            steps.append(("swipe", {"x1": gx, "y1": gy, "x2": ex, "y2": ey,
                                    "duration_ms": self.timing.get("swipe_duration_ms", 300)}))
            steps.append(("wait", {"ms": self.timing.get("deploy_settle_ms", 500)}))
            return steps

        if action.action == "skill":
            idx = (action.skill_id or 0) - 1
            if not (0 <= idx < len(self.skill_buttons)):
                raise ValueError("技能按钮坐标未校准：coords.skill_buttons 未配置 skill_id=%s"
                                 "（configs/perception.yaml 当前为空占位）" % action.skill_id)
            # 占位手势：直接点技能按钮。
            # TODO 真机校准：真机通常先点已部署干员选中，再点其技能按钮。
            x, y = self.skill_buttons[idx]
            steps.append(("tap", {"x": int(x), "y": int(y)}))
            steps.append(("wait", {"ms": self.timing.get("skill_settle_ms", 300)}))
            return steps

        if action.action == "retreat":
            cell = self.deployed_cell_resolver(action.operator_id) \
                if self.deployed_cell_resolver else None
            if not cell:
                raise ValueError("未知干员 %r 的已部署格子（deployed_cell_resolver 返回空），"
                                 "无法撤退" % action.operator_id)
            gx, gy = self.grid.grid_to_pixel(cell)
            rx, ry = self.grid.retreat_button(gx, gy)
            steps.append(("tap", {"x": gx, "y": gy}))       # 选中干员
            steps.append(("wait", {"ms": self.timing.get("tap_settle_ms", 80)}))
            steps.append(("tap", {"x": rx, "y": ry}))       # 点撤退按钮
            return steps

        raise ValueError("未知动作类型：%r" % action.action)

    # ---------- 下发 ----------
    def _dispatch(self, kind, kwargs):
        if kind == "tap":
            return self.ctrl.tap(**kwargs)
        if kind == "swipe":
            return self.ctrl.swipe(**kwargs)
        if kind == "wait":
            self._sleep(kwargs.get("ms", 0))
            return None
        raise ValueError("未知原语：%s" % kind)

    def _execute_one(self, index, action):
        # type: (int, Action) -> ActionResult
        ops = []  # type: List[str]
        try:
            steps = self._compile(action)
        except ValueError as exc:
            return ActionResult(index=index, action=action.action, success=False,
                                status="error", error=str(exc), ops=ops)
        for kind, kwargs in steps:
            if kind == "wait":
                self._dispatch(kind, kwargs)
                ops.append("wait")
                continue
            try:
                r = self._dispatch(kind, kwargs)
            except ADBControllerError as exc:   # 连接级错误：该动作失败
                return ActionResult(index=index, action=action.action, success=False,
                                    status="offline", error=str(exc), ops=ops)
            ops.append(r.op)
            if not r.success:
                return ActionResult(index=index, action=action.action, success=False,
                                    status=r.status, error=r.error, ops=ops)
        return ActionResult(index=index, action=action.action, success=True,
                            status="ok", ops=ops)

    def execute(self, plan):
        # type: (ActionPlan) -> PlanResult
        if isinstance(plan, list):
            plan = ActionPlan(actions=plan)
        results = []
        succeeded = failed = 0
        between = self.timing.get("between_actions_ms", 100)
        for i, action in enumerate(plan.actions):
            self.action_log.append(action)
            ar = self._execute_one(i, action)
            results.append(ar)
            if ar.success:
                succeeded += 1
            else:
                failed += 1          # 失败仅记录，继续后续动作
            if i < len(plan.actions) - 1:
                self._sleep(between)
        return PlanResult(total=len(plan.actions), succeeded=succeeded, failed=failed,
                          completed=True, results=results)


class MockActionExecutor(ActionExecutor):
    """CPU 闭环：自动配 MockADBController、不真实 sleep、只记录。

    card_slots / deployed_cells 传入最小 mock 手牌/部署信息以便部署、撤退走通：
      card_slots={"翎羽": 0}  deployed_cells={"芬": "E4"}
    """

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH,
                 card_slots=None, deployed_cells=None):
        self.mock_controller = MockADBController()
        card_slots = dict(card_slots or {})
        deployed_cells = dict(deployed_cells or {})
        super(MockActionExecutor, self).__init__(
            self.mock_controller, config=config, config_path=config_path,
            card_slot_resolver=lambda name: card_slots.get(name),
            deployed_cell_resolver=lambda name: deployed_cells.get(name),
            real_sleep=False)

    def device_ops(self):
        return self.mock_controller.ops()
