# -*- coding: utf-8 -*-
"""action 包单元测试。

契约/边界用例恒跑（纯 CPU，Mock 控制器）；
真实 ADBController 在无 adb 可执行文件/无设备时自动 skip。
"""
import os
import shutil
import sys

import pytest
from pydantic import ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from action import (Action, ActionExecutor, ActionPlan, ADBController,
                    ADBControllerError, GridConverter, MockActionExecutor,
                    MockADBController, OpResult, load_action_config, parse_cell)  # noqa: E402


# ---------------------------------------------------------------- 动作契约
class TestActionSchema:
    def test_deploy_valid(self):
        a = Action(action="deploy", operator_id="翎羽", grid_pos="A3", direction="left")
        assert a.grid_pos == "A3" and a.direction == "left"

    def test_deploy_requires_operator_and_cell(self):
        with pytest.raises(ValidationError):
            Action(action="deploy", grid_pos="A3")
        with pytest.raises(ValidationError):
            Action(action="deploy", operator_id="x", grid_pos="@@@")

    def test_deploy_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            Action(action="deploy", operator_id="x", grid_pos="A3", skill_id=1)
        with pytest.raises(ValidationError):
            Action(action="deploy", operator_id="x", grid_pos="A3", duration_ms=10)

    def test_skill_valid_and_range(self):
        Action(action="skill", operator_id="芬", skill_id=3)
        with pytest.raises(ValidationError):
            Action(action="skill", operator_id="芬")            # 缺 skill_id
        with pytest.raises(ValidationError):
            Action(action="skill", operator_id="芬", skill_id=0)
        with pytest.raises(ValidationError):
            Action(action="skill", operator_id="芬", skill_id=4)
        with pytest.raises(ValidationError):
            Action(action="skill", operator_id="芬", skill_id=1, grid_pos="A1")

    def test_retreat(self):
        a = Action(action="retreat", operator_id="芬")
        assert a.operator_id == "芬"
        with pytest.raises(ValidationError):
            Action(action="retreat")
        with pytest.raises(ValidationError):
            Action(action="retreat", operator_id="芬", grid_pos="E4")

    def test_wait(self):
        Action(action="wait", duration_ms=0)
        Action(action="wait", duration_ms=60000)
        with pytest.raises(ValidationError):
            Action(action="wait")                              # 缺时长
        with pytest.raises(ValidationError):
            Action(action="wait", duration_ms=-1)
        with pytest.raises(ValidationError):
            Action(action="wait", duration_ms=60001)           # 超上限
        with pytest.raises(ValidationError):
            Action(action="wait", duration_ms=100, operator_id="x")

    def test_bad_action_type(self):
        with pytest.raises(ValidationError):
            Action(action="dance", duration_ms=1)

    def test_empty_operator_id_rejected(self):
        with pytest.raises(ValidationError):
            Action(action="deploy", operator_id="   ", grid_pos="A1")


# ---------------------------------------------------------------- 坐标转换
class TestGridConverter:
    def test_parse_cell(self):
        assert parse_cell("A1") == (0, 0)
        assert parse_cell("A3") == (0, 2)
        assert parse_cell("B2") == (1, 1)
        assert parse_cell("AA1") == (26, 0)
        assert parse_cell(" a3 ") == (0, 2)
        for bad in ["@@@", "12A", "", "A", "3"]:
            with pytest.raises(ValueError):
                parse_cell(bad)

    def test_grid_to_pixel_matches_config(self):
        cfg = load_action_config()
        conv = GridConverter(cfg)
        origin = tuple(cfg["coords"]["grid"]["origin"])
        step = tuple(cfg["coords"]["grid"]["cell"])
        assert conv.grid_to_pixel("A1") == (origin[0], origin[1])
        assert conv.grid_to_pixel("A3") == (origin[0], origin[1] + 2 * step[1])
        assert conv.grid_to_pixel("B2") == (origin[0] + step[0], origin[1] + step[1])

    def test_grid_out_of_range(self):
        conv = GridConverter()
        # 10x10：列 A-J、行 1-10；K1 / A11 越界，J10 是最后一个合法格
        assert conv.grid_to_pixel("J10")
        with pytest.raises(ValueError):
            conv.grid_to_pixel("K1")
        with pytest.raises(ValueError):
            conv.grid_to_pixel("A11")

    def test_card_slot_center(self):
        cfg = load_action_config()
        conv = GridConverter(cfg)
        x1, y1, x2, y2 = cfg["coords"]["operator_card_bar"]
        count = cfg["cards"]["count"]
        x, y = conv.card_slot_center(0)
        assert x1 <= x <= x2 and y1 <= y <= y2
        assert y == (y1 + y2) // 2
        # 等分单调递增
        xs = [conv.card_slot_center(i)[0] for i in range(count)]
        assert xs == sorted(xs) and len(set(xs)) == count
        with pytest.raises(ValueError):
            conv.card_slot_center(count)


# ---------------------------------------------------------------- 执行器（mock）
class TestMockExecution:
    def _cfg_with_skill_button(self):
        cfg = load_action_config()
        cfg["coords"]["skill_buttons"] = [[100, 100], [200, 100], [300, 100]]
        return cfg

    def test_wait_only(self):
        ex = MockActionExecutor()
        res = ex.execute(ActionPlan(actions=[Action(action="wait", duration_ms=50)]))
        assert res.total == 1 and res.succeeded == 1 and res.all_success
        assert res.results[0].ops == ["wait"]

    def test_deploy_compiles_tap_and_swipe(self):
        ex = MockActionExecutor(card_slots={"翎羽": 0})
        plan = ActionPlan(actions=[
            Action(action="deploy", operator_id="翎羽", grid_pos="A3", direction="left")])
        res = ex.execute(plan)
        assert res.all_success
        ops = res.results[0].ops
        assert ops[0] == "tap" and "swipe" in ops
        # 底层确实记录了坐标
        taps = [r for r in ex.mock_controller.log if r.op == "tap"]
        swipes = [r for r in ex.mock_controller.log if r.op == "swipe"]
        assert taps and swipes
        s = swipes[0]
        assert s.detail["x2"] < s.detail["x1"]     # 朝左滑
        assert len(ex.action_log) == 1

    def test_deploy_unknown_operator_fails_with_reason(self):
        ex = MockActionExecutor(card_slots={"翎羽": 0})
        res = ex.execute(ActionPlan(actions=[
            Action(action="deploy", operator_id="不存在", grid_pos="A3")]))
        assert res.failed == 1 and not res.all_success
        r = res.results[0]
        assert r.status == "error" and "卡槽位" in r.error

    def test_retreat_needs_deployed_cell(self):
        ex = MockActionExecutor(deployed_cells={"芬": "E4"})
        res = ex.execute(ActionPlan(actions=[Action(action="retreat", operator_id="芬")]))
        assert res.all_success and res.results[0].ops.count("tap") == 2

        ex2 = MockActionExecutor()
        res2 = ex2.execute(ActionPlan(actions=[Action(action="retreat", operator_id="芬")]))
        assert res2.failed == 1 and "已部署格子" in res2.results[0].error

    def test_skill_button_unconfigured_fails_clearly(self):
        ex = MockActionExecutor()       # 默认 coords.skill_buttons 为空
        res = ex.execute(ActionPlan(actions=[
            Action(action="skill", operator_id="芬", skill_id=1)]))
        assert res.failed == 1 and "未校准" in res.results[0].error

    def test_skill_success_when_configured(self):
        cfg = self._cfg_with_skill_button()
        ex = MockActionExecutor(config=cfg)
        res = ex.execute(ActionPlan(actions=[
            Action(action="skill", operator_id="芬", skill_id=2)]))
        assert res.all_success
        tap = [r for r in ex.mock_controller.log if r.op == "tap"][0]
        assert (tap.detail["x"], tap.detail["y"]) == (200, 100)

    def test_batch_failure_does_not_abort_plan(self):
        ex = MockActionExecutor(card_slots={"翎羽": 0}, deployed_cells={"芬": "E4"})
        plan = ActionPlan(actions=[
            Action(action="deploy", operator_id="翎羽", grid_pos="A2", direction="up"),
            Action(action="skill", operator_id="芬", skill_id=1),   # 未配置技能键 => 失败
            Action(action="wait", duration_ms=0),
            Action(action="retreat", operator_id="芬"),
        ])
        res = ex.execute(plan)
        assert res.completed and res.total == 4
        assert res.succeeded == 3 and res.failed == 1
        assert [r.action for r in res.results] == ["deploy", "skill", "wait", "retreat"]
        assert res.results[1].status == "error"
        # 失败后 wait/retreat 仍执行
        assert res.results[2].success and res.results[3].success

    def test_accepts_plain_list(self):
        ex = MockActionExecutor()
        res = ex.execute([Action(action="wait", duration_ms=0)])
        assert res.total == 1 and res.all_success


# ---------------------------------------------------------------- Mock 控制器
class TestMockController:
    def test_record_and_offline(self):
        c = MockADBController()
        assert c.online()
        r = c.tap(10, 20)
        assert isinstance(r, OpResult) and r.success and r.detail == {"x": 10, "y": 20}
        c.swipe(1, 2, 3, 4, 300)
        c.key(4)
        assert c.ops() == ["tap", "swipe", "key"]
        c.set_online(False)
        off = c.tap(1, 1)
        assert not off.success and off.status == "offline"
        with pytest.raises(ADBControllerError):
            c.screencap_png()

    def test_screencap_mock_returns_empty(self):
        c = MockADBController()
        assert c.screencap_png() == b""
        assert c.ops() == ["screencap"]


# ---------------------------------------------------------------- 真实控制器（有设备才跑）
HAS_ADB = shutil.which("adb") is not None


@pytest.mark.skipif(not HAS_ADB, reason="环境无 adb，跳过真实设备用例")
class TestRealADBController:
    def test_connect_and_tap_requires_device(self):
        ctrl = ADBController()
        try:
            ctrl.connect()
        except ADBControllerError:
            pytest.skip("无在线 MuMu/adb 设备")
        assert ctrl.online()
        r = ctrl.tap(1, 1)         # 点角落，避免误触
        assert r.success
