# TODO-V100: 抽卡界面真实识别依赖 OCR（合成玉/源石/凭证/卡池名）与模板/VLM，V100/真机填实现。
"""抽卡（寻访）界面解析（第十五批 任务二·2）。"""

from typing import Optional

from pydantic import BaseModel, Field

from .menu_io import MENU_EVIDENCE_MOCK

__all__ = ["GachaState", "MockGachaScreenParser", "GachaScreenParser"]


class GachaState(BaseModel):
    on_banner_page: bool = False
    banner_name: str = ""
    orundum: Optional[int] = None        # 合成玉
    originite: Optional[int] = None      # 至纯源石
    tickets: Optional[int] = None        # 寻访凭证（折算单抽券）
    can_single: bool = False
    can_ten: bool = False
    confidence: float = 0.0
    evidence: str = MENU_EVIDENCE_MOCK
    note: str = ""


class MockGachaScreenParser(object):
    """固定假状态：已在卡池页，资源够十连。"""

    def __init__(self, config=None):
        self.config = config

    def parse(self, frame=None):
        return GachaState(
            on_banner_page=True,
            banner_name="标准寻访（mock）",
            orundum=12000, originite=18, tickets=2,
            can_single=True, can_ten=True,
            confidence=1.0, evidence=MENU_EVIDENCE_MOCK,
            note="mock 固定状态：资源充足，可单抽/十连")


class GachaScreenParser(object):
    def __init__(self, config=None):
        self.config = config

    def parse(self, frame=None):
        # TODO-V100：OCR 识别 roi（orundum/originite/tickets/banner_title，见 menu.yaml），
        # 模板判断单抽/十连按钮是否可点；真实坐标待真机校准。
        raise NotImplementedError(
            "TODO-V100: GachaScreenParser 真实识别待接入 OCR/模板（并校准 configs/menu.yaml）")
