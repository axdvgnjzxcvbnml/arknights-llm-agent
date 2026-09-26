"""登录/签到/抽卡/商店 视觉+动作骨架单元测试（第十五批 任务二·2）。

契约与边界恒跑（mock）；真实视觉解析用例断言 NotImplementedError；不接触真机/ADB。
"""

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from perception.login import (  # noqa: E402
    LoginState, MockLoginScreenParser, LoginScreenParser)
from perception.gacha import (  # noqa: E402
    GachaState, MockGachaScreenParser, GachaScreenParser)
from perception.shop import (  # noqa: E402
    ShopState, MockShopScreenParser, ShopScreenParser)
from perception.menu_io import load_menu_config, is_calibrated  # noqa: E402
from action.adb_controller import MockADBController  # noqa: E402
from action.menu_actions import (  # noqa: E402
    MenuAction, MenuActionExecutor, MockMenuActionExecutor, MENU_ACTION_KINDS)


class TestMenuParsers:
    def test_mock_login_state(self):
        s = MockLoginScreenParser().parse()
        assert isinstance(s, LoginState)
        assert s.logged_in and s.announcement_open and s.daily_checkin_available
        assert s.evidence == "mock"

    def test_mock_gacha_state(self):
        s = MockGachaScreenParser().parse()
        assert isinstance(s, GachaState)
        assert s.on_banner_page and s.can_ten and s.orundum == 12000
        assert s.evidence == "mock"

    def test_mock_shop_state(self):
        s = MockShopScreenParser().parse()
        assert isinstance(s, ShopState)
        assert s.free_daily_available and any(i.free for i in s.items)
        assert s.evidence == "mock"

    @pytest.mark.parametrize("parser_cls",
                             [LoginScreenParser, GachaScreenParser, ShopScreenParser])
    def test_real_parsers_are_skeletons(self, parser_cls):
        with pytest.raises(NotImplementedError, match="TODO-V100"):
            parser_cls().parse(frame=None)

    def test_config_placeholder_uncalibrated(self):
        cfg = load_menu_config()
        assert is_calibrated(cfg) is False  # 提交的占位配置必须保持未校准


class TestMenuActions:
    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            MenuAction(kind="hack_everything")

    def test_all_kinds_mapped(self):
        # 15 个逻辑动作都在按钮映射里
        assert len(MENU_ACTION_KINDS) == 16
        for k in MENU_ACTION_KINDS:
            MenuAction(kind=k)

    def test_mock_executor_records_sequence(self):
        ctrl = MockADBController()
        ex = MockMenuActionExecutor(controller=ctrl)
        seq = [
            MenuAction(kind="close_announcement"),
            MenuAction(kind="claim_daily_checkin"),
            MenuAction(kind="open_gacha"),
            MenuAction(kind="gacha_pull_ten"),
            MenuAction(kind="gacha_confirm"),
        ]
        results = ex.execute_all(seq)
        assert [r.status for r in results] == ["ok"] * 5
        assert ex.executed_kinds() == [
            "close_announcement", "claim_daily_checkin",
            "open_gacha", "gacha_pull_ten", "gacha_confirm"]
        # 每个动作在 mock 控制器上各记一次占位点击
        taps = [o for o in ctrl.ops() if o == "tap"]
        assert len(taps) == 5
        # mock 不返回真机坐标
        assert all(r.screen_point is None for r in results)

    def test_real_executor_refuses_placeholder_uncalibrated(self):
        cfg = load_menu_config()  # calibrated=False, 全是 -1
        ctrl = MockADBController()
        ex = MenuActionExecutor(controller=ctrl, config=cfg)
        r = ex.execute(MenuAction(kind="gacha_pull_ten"))
        assert r.status == "fail" and "校准" in r.message
        assert ctrl.ops() == []  # 拒绝时不应有任何点击

    def test_real_executor_taps_when_calibrated(self):
        cfg = {
            "calibrated": True,
            "gacha": {"buttons": {"pull_ten": [1200, 620], "confirm": [640, 480]}},
            "login": {"buttons": {}}, "shop": {"buttons": {}},
        }
        ctrl = MockADBController()
        ex = MenuActionExecutor(controller=ctrl, config=cfg)
        r = ex.execute(MenuAction(kind="gacha_pull_ten"))
        assert r.status == "ok" and r.screen_point == [1200, 620]
        assert ctrl.ops()[0] == "tap"

    def test_calibrated_but_still_placeholder_point_refused(self):
        cfg = {"calibrated": True,
               "gacha": {"buttons": {"pull_ten": [-1, -1]}},
               "login": {"buttons": {}}, "shop": {"buttons": {}}}
        ex = MenuActionExecutor(controller=MockADBController(), config=cfg)
        r = ex.execute(MenuAction(kind="gacha_pull_ten"))
        assert r.status == "fail"
