# TODO-V100: 商店界面真实识别依赖 OCR + 模板/VLM，V100/真机填实现。
"""商店界面解析（第十五批 任务二·2）。"""

from typing import List, Optional

from pydantic import BaseModel, Field

from .menu_io import MENU_EVIDENCE_MOCK

__all__ = ["ShopItem", "ShopState", "MockShopScreenParser", "ShopScreenParser"]


class ShopItem(BaseModel):
    item_id: str
    name: str = ""
    price: Optional[int] = None
    currency: str = ""          # orundum/originite/lmd/credits/...
    free: bool = False          # 是否免费（每日免费）
    sold_out: bool = False


class ShopState(BaseModel):
    on_shop_page: bool = False
    free_daily_available: bool = False
    items: List[ShopItem] = Field(default_factory=list)
    confidence: float = 0.0
    evidence: str = MENU_EVIDENCE_MOCK
    note: str = ""


class MockShopScreenParser(object):
    def __init__(self, config=None):
        self.config = config

    def parse(self, frame=None):
        return ShopState(
            on_shop_page=True,
            free_daily_available=True,
            items=[
                ShopItem(item_id="daily_free", name="每日免费补给", free=True),
                ShopItem(item_id="lmd_pack", name="龙门币礼包", price=1000,
                         currency="credits"),
            ],
            confidence=1.0, evidence=MENU_EVIDENCE_MOCK,
            note="mock 固定状态：每日免费可领")


class ShopScreenParser(object):
    def __init__(self, config=None):
        self.config = config

    def parse(self, frame=None):
        # TODO-V100：OCR 识别商品名/价格/货币，模板判断免费角标与售罄；坐标待真机校准。
        raise NotImplementedError(
            "TODO-V100: ShopScreenParser 真实识别待接入 OCR/模板（并校准 configs/menu.yaml）")
