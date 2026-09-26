# TODO-V100: 非对战菜单动作依赖 configs/menu.yaml 真机坐标校准；占位配置下真实执行拒绝盲点。
"""非对战界面动作：登录/签到/抽卡/商店（第十五批 任务二·2）。

- 复用 action/adb_controller.py 的 ADBController / MockADBController（tap/key/swipe）；
- 动作只是"在某个逻辑按钮上点一下"，坐标从 configs/menu.yaml 读取，不硬编码；
- 真实坐标当前是占位且 calibrated=false，真实执行器会**拒绝点击**并明确报错（防盲点）；
- MockMenuActionExecutor 不看坐标、只记录逻辑动作，供 CPU 闭环测试。
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .adb_controller import MockADBController
from perception.menu_io import (
    DEFAULT_CONFIG_PATH, is_calibrated, is_placeholder_point, load_menu_config)

__all__ = [
    "MENU_ACTION_KINDS", "MenuAction", "MenuActionResult",
    "MenuActionExecutor", "MockMenuActionExecutor",
]

# kind -> (配置节, 按钮键)
_BUTTON_MAP = {
    # 登录 / 公告 / 签到
    "login_confirm": ("login", "login_confirm"),
    "tap_to_continue": ("login", "tap_to_continue"),
    "close_announcement": ("login", "announcement_close"),
    "open_checkin": ("login", "checkin_entry"),
    "claim_daily_checkin": ("login", "checkin_claim"),
    "close_checkin": ("login", "checkin_close"),
    # 抽卡
    "open_gacha": ("gacha", "gacha_entry"),
    "select_normal_banner": ("gacha", "tab_normal"),
    "gacha_pull_single": ("gacha", "pull_single"),
    "gacha_pull_ten": ("gacha", "pull_ten"),
    "gacha_confirm": ("gacha", "confirm"),
    "gacha_back": ("gacha", "back"),
    # 商店
    "open_shop": ("shop", "shop_entry"),
    "claim_free_daily": ("shop", "free_daily"),
    "shop_buy_confirm": ("shop", "buy_confirm"),
    "shop_back": ("shop", "back"),
}

MENU_ACTION_KINDS = tuple(sorted(_BUTTON_MAP.keys()))


class MenuAction(BaseModel):
    kind: Literal[MENU_ACTION_KINDS]  # type: ignore
    wait_after_ms: int = Field(0, ge=0, description="点击后等待（真机动画），mock 不睡")
    note: str = ""


class MenuActionResult(BaseModel):
    kind: str
    status: str = "ok"               # ok / fail / skipped
    section: str = ""
    button: str = ""
    screen_point: Optional[List[int]] = None   # 真机校准后的实际点击点；mock 为 None
    message: str = ""


class MenuActionExecutor(object):
    """真实菜单动作执行器：坐标未校准则拒绝执行，不盲点。"""

    def __init__(self, controller=None, config=None, config_path=DEFAULT_CONFIG_PATH):
        self.config = config or load_menu_config(config_path)
        if controller is None:
            from .adb_controller import ADBController
            controller = ADBController()
        self.controller = controller

    def _resolve(self, action):
        section, button = _BUTTON_MAP[action.kind]
        point = self.config.get(section, {}).get("buttons", {}).get(button)
        return section, button, point

    def execute(self, action):
        section, button, point = self._resolve(action)
        if not is_calibrated(self.config) or is_placeholder_point(point):
            return MenuActionResult(
                kind=action.kind, status="fail", section=section, button=button,
                message="坐标为占位/未真机校准（configs/menu.yaml calibrated=false），"
                        "拒绝盲点；请先在真机校准后再执行")
        op = self.controller.tap(int(point[0]), int(point[1]))
        status = getattr(op, "status", "ok")
        return MenuActionResult(
            kind=action.kind, status=status if status == "ok" else "fail",
            section=section, button=button, screen_point=[int(point[0]), int(point[1])],
            message=getattr(op, "error", "") or "")

    def execute_all(self, actions):
        # 单个失败不中断整段（与 ActionExecutor 一致），返回逐条结果
        return [self.execute(a) for a in actions]


class MockMenuActionExecutor(MenuActionExecutor):
    """mock：不看坐标、不校准，记录逻辑动作到 log，供 CPU 闭环。"""

    def __init__(self, controller=None, config=None):
        self.config = config or _mock_menu_config()
        self.controller = controller or MockADBController()
        self.log = []  # type: list

    def execute(self, action):
        section, button, _ = self._resolve(action)
        self.log.append({"kind": action.kind, "section": section, "button": button})
        # 在 mock 控制器上记一次占位点击（不接触真机）
        self.controller.tap(0, 0)
        return MenuActionResult(
            kind=action.kind, status="ok", section=section, button=button,
            screen_point=None, message="mock executed")

    def executed_kinds(self):
        return [x["kind"] for x in self.log]


def _mock_menu_config():
    try:
        return load_menu_config()
    except Exception:
        return {"calibrated": False, "login": {"buttons": {}},
                "gacha": {"buttons": {}}, "shop": {"buttons": {}}}
