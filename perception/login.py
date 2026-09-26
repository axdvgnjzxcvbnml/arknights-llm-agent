# TODO-V100: 登录/公告/每日签到的真实界面识别依赖 OCR + 模板/VLM，V100（或真机）阶段填实现。
"""登录 / 公告 / 每日签到界面解析（第十五批 任务二·2）。

分层（与 ocr_cost/map_parser 一致）：
- Pydantic 契约 LoginState；
- MockLoginScreenParser：固定假状态，CPU 闭环恒跑；
- LoginScreenParser：真实识别骨架，调用即 NotImplementedError（待真机+模型）。

import 本模块不拉起 torch / opencv / numpy。
"""

from pydantic import BaseModel, Field

from .menu_io import MENU_EVIDENCE_MOCK, MENU_EVIDENCE_REAL

__all__ = ["LoginState", "MockLoginScreenParser", "LoginScreenParser"]


class LoginState(BaseModel):
    """登录/大厅/签到相关界面状态。"""

    screen: str = Field("unknown", description="login|announcement|lobby|loading|unknown")
    logged_in: bool = False
    announcement_open: bool = False
    daily_checkin_available: bool = False  # 今日签到是否还没领
    can_tap_to_continue: bool = False
    confidence: float = 0.0
    evidence: str = MENU_EVIDENCE_MOCK      # mock / cv / vlm
    note: str = ""


class MockLoginScreenParser(object):
    """固定假状态：已进大厅、有公告弹窗、今日签到可领。"""

    def __init__(self, config=None):
        self.config = config

    def parse(self, frame=None):
        return LoginState(
            screen="announcement",
            logged_in=True,
            announcement_open=True,
            daily_checkin_available=True,
            can_tap_to_continue=True,
            confidence=1.0,
            evidence=MENU_EVIDENCE_MOCK,
            note="mock 固定状态：公告弹窗待关闭、签到可领")


class LoginScreenParser(object):
    """真实登录界面识别（OCR 数字 + 模板匹配按钮）。骨架，V100/真机填实现。"""

    def __init__(self, config=None):
        self.config = config

    def parse(self, frame=None):
        # TODO-V100：用 PaddleOCR 识别"开始游戏/点击进入"，模板匹配公告关闭与签到入口；
        # 真实坐标/roi 从 configs/menu.yaml 读取（当前为占位，待真机校准）。
        raise NotImplementedError(
            "TODO-V100: LoginScreenParser 真实识别待接入 OCR/模板（并校准 configs/menu.yaml）")
