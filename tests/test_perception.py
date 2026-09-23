"""perception 视觉解析单元测试。

本文件随第三批各模块逐步扩充。分层：
- 契约/组装/mock 用例恒跑（不依赖 GPU、模拟器、真实截图）；
- adb 真机用例仅在 adb 与在线设备就绪时运行，否则 skip；
- 任何 YOLO/OCR/VLM 真实推理用例在无权重/GPU 时 skip。

运行：python -m pytest tests/test_perception.py -v
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.chdir(str(ROOT))


class TestNoHeavyImports:
    def test_importing_perception_does_not_load_gpu_stack(self):
        for m in list(sys.modules):
            assert not m.startswith("ultralytics")
            assert not m.startswith("paddleocr")
        import perception  # noqa: F401
        from perception import screen_capture, state_parser  # noqa: F401
        # numpy 是允许的轻量依赖；torch/paddle/ultralytics 不应被 import 拉起
        assert "torch" not in sys.modules
        assert "ultralytics" not in sys.modules
        assert "paddleocr" not in sys.modules


class TestConfigAndGrid:
    def test_config_loads_sections(self):
        from perception.config import load_perception_config
        cfg = load_perception_config()
        for s in ("adb", "capture", "coords", "models", "spawn"):
            assert s in cfg
        assert cfg["adb"]["port"] in (7555, 16384, 16416)  # MuMu 常见端口

    def test_cell_id_naming(self):
        from perception.state_parser import cell_id
        assert cell_id(0, 0) == "A1"
        assert cell_id(0, 4) == "A5"
        assert cell_id(1, 4) == "B5"
        assert cell_id(25, 0) == "Z1"
        assert cell_id(26, 0) == "AA1"

    def test_build_grid_deployable(self):
        from perception.state_parser import build_grid
        g = build_grid(10, 10, blocked={(3, 6)}, occupied={(2, 2)},
                       highland={(7, 0)})
        ids = g.deployable_ids()
        # A/B 前 5 格全部可部署，与 state_to_text 示例一致
        for cid in ["A1", "A2", "A3", "A4", "A5", "B1", "B5"]:
            assert cid in ids
        assert "C3" not in ids           # occupied
        blocked = {c.cell_id: c for c in g.cells}["D7"]
        assert blocked.terrain == "blocked" and not blocked.deployable
        high = {c.cell_id: c for c in g.cells}["H1"]
        assert high.terrain == "highland" and high.deployable


class TestMockScreenCapture:
    def test_synthetic_frame_shape_dtype(self):
        from perception.screen_capture import MockScreenCapture
        cap = MockScreenCapture()
        f = cap.capture()
        assert f.shape == (720, 1280, 3)
        assert f.dtype.name == "uint8"

    def test_deterministic(self):
        import numpy as np
        from perception.screen_capture import MockScreenCapture
        a = MockScreenCapture(frame_index=0).capture()
        b = MockScreenCapture(frame_index=0).capture()
        assert np.array_equal(a, b)
        seq = MockScreenCapture(frame_index=0)
        assert seq.frame_index == 0
        seq.capture()
        assert seq.frame_index == 1

    def test_capture_with_meta(self):
        from perception.screen_capture import MockScreenCapture
        cap = MockScreenCapture()
        frame, meta = cap.capture_with_meta()
        assert meta.source == "mock" and meta.width == frame.shape[1]
        assert "cv2" not in sys.modules  # 纯 numpy 合成不应拉起 opencv


class TestADBScreenCapture:
    def _device_online(self, adb):
        import subprocess
        try:
            out = subprocess.run([adb.adb_path, "devices"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=10
                                 ).stdout.decode("utf-8", "ignore")
        except Exception:
            return False
        return any(l.startswith(adb.serial + "\t") and "\tdevice" in l
                   for l in out.splitlines())

    def test_connect_without_device_is_friendly_error(self):
        from perception.screen_capture import ADBScreenCapture, ScreenCaptureError
        adb = ADBScreenCapture()
        if adb.is_available() and self._device_online(adb):
            pytest.skip("检测到在线设备，跳过无设备异常用例")
        with pytest.raises(ScreenCaptureError):
            adb.connect()

    def test_unknown_backend(self):
        from perception.screen_capture import get_screen_capture
        with pytest.raises(ValueError):
            get_screen_capture("vnc")


class TestSpawnTracker:
    def test_estimated_plan_from_stage_dict(self):
        from perception.state_parser import SpawnTracker
        cfg = {"spawn": {"default_spawn_interval_sec": 6.0, "timeline": {}}}
        tr = SpawnTracker(config=cfg)
        stage = {"enemies": [{"名称": "源石虫", "数量": 3},
                             {"名称": "猎犬", "数量": 2}]}
        plan, timing = tr.build_plan("3-8", stage)
        assert timing == "estimated"
        assert [(p.enemy, p.count) for p in plan] == [("源石虫", 3), ("猎犬", 2)]
        assert [p.expected_time_sec for p in plan] == [0.0, 6.0]
        # elapsed=3：只有第一组到点
        _, presence = SpawnTracker.update(plan, 3.0)
        assert {p.name: p.observed_count for p in presence} == {"源石虫": 3}

    def test_annotated_timeline_and_confirmation(self):
        from perception.state_parser import SpawnTracker
        cfg = {"spawn": {"timeline": {"3-8": [
            {"time_sec": 5, "enemy": "源石虫", "count": 3},
            {"time_sec": 40, "enemy": "碎骨", "count": 1}]}}}
        tr = SpawnTracker(config=cfg)
        plan, timing = tr.build_plan("3-8")
        assert timing == "annotated"
        # 40s 且源石虫被 CV 确认
        plan, presence = SpawnTracker.update(plan, 40.0, {"源石虫": True})
        src = {p.name: p.source for p in presence}
        assert src["源石虫"] == "cv"
        assert src["碎骨"] == "timer:annotated"
        assert plan[0].appeared and plan[0].confirmed_by == "cv"

    def test_iter_stage_enemies_duck_types(self):
        from perception.state_parser import iter_stage_enemies

        class Row(object):
            def __init__(s, name, count):
                s.name = name
                s.count = count

        class Obj(object):
            enemies = [Row("碎骨", 1)]
        assert iter_stage_enemies(Obj()) == [("碎骨", 1)]
        assert iter_stage_enemies(None) == []
        bad = {"enemies": [{"名称": "x", "数量": ""}]}
        assert iter_stage_enemies(bad) == [("x", 1)]


class TestStateParser:
    def test_assemble_game_state_contract(self):
        from perception.schemas import (CostStatus, FrameMeta, GameMap,
                                        OperatorCard)
        from perception.state_parser import StateParser, build_grid
        parser = StateParser()
        gs = parser.assemble(
            frame_meta=FrameMeta(width=1280, height=720, source="mock"),
            stage_id="1-1", cost=CostStatus(current=9, source="mock"),
            operator_cards=[OperatorCard(name="芬", operator_class="先锋", cost=2)],
            game_map=build_grid(10, 10))
        d = gs.model_dump()
        import json
        json.dumps(d, ensure_ascii=False)  # 可序列化
        assert gs.cost.current == 9 and gs.game_map.cols == 10

    def test_real_parse_uses_timer(self):
        from perception.state_parser import SpawnTracker, StateParser
        cfg = {"spawn": {"default_spawn_interval_sec": 6.0, "timeline": {}}}
        tracker = SpawnTracker(config=cfg)
        parser = StateParser(config={
            "capture": {"width": 1280, "height": 720, "channels": 3},
            "coords": {"grid": {"cols": 10, "rows": 10}}})
        stage = {"enemies": [{"名称": "源石虫", "数量": 3},
                             {"名称": "猎犬", "数量": 2}]}
        gs = parser.parse(frame_meta=None, stage_id="3-8", elapsed_sec=7.0,
                          spawn_tracker=tracker, stage_info=stage)
        names = {e.name for e in gs.enemies_on_field}
        assert names == {"源石虫", "猎犬"}
        assert gs.timing_source == "estimated" and gs.notes


class TestMockStateParser:
    def test_mock_state_matches_text_example(self):
        from perception.state_parser import MockStateParser
        gs = MockStateParser().get_state(elapsed_sec=12.0)
        assert gs.stage_id == "3-8"
        assert gs.cost.current == 15
        assert [(c.operator_class, c.cost) for c in gs.operator_cards] == \
            [("先锋", 2), ("狙击", 3), ("医疗", 3)]
        assert gs.life_points == 3 and gs.deploy_limit == 9
        # 地图 A1-A5 / B1-B5 可部署
        ids = set(gs.game_map.deployable_ids())
        assert all(cid in ids for cid in
                   ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"])
        # 敌人从左侧来，含重装；计时估算
        assert gs.enemies_on_field
        assert all(e.position_hint == "左侧" for e in gs.enemies_on_field)
        heavy = [e for e in gs.enemies_on_field if e.name == "重装敌人"]
        assert heavy and heavy[0].observed_count == 3
        assert gs.timing_source == "estimated"
        # 源石虫被标为 cv 确认，其余为 timer 估算
        src = {e.name: e.source for e in gs.enemies_on_field}
        assert src["源石虫"] == "cv"
        assert src["重装敌人"] == "timer:estimated"
