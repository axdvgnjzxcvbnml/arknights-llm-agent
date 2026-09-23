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
        # 用干净子进程验证：同一 pytest 进程里其他测试（如 RAG）可能已合法加载 torch，
        # 进程内断言会被污染；子进程才能准确证明"import perception 本身不拉起 GPU 栈"。
        import subprocess
        code = (
            "import sys; import perception; "
            "from perception import screen_capture, state_parser, ocr_cost, "
            "map_parser, detector_yolo, vlm_analyzer, state_to_text; "
            "banned = ['torch', 'ultralytics', 'paddleocr', 'transformers', 'cv2']; "
            "hit = [m for m in banned if m in sys.modules]; "
            "print('HEAVY:' + ','.join(hit))")
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True)
        assert proc.returncode == 0, proc.stderr
        assert "HEAVY:" in proc.stdout
        loaded = proc.stdout.split("HEAVY:", 1)[1].strip()
        assert loaded == "", "import perception 拉起了重依赖: %s" % loaded


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
        # 地图恰为固定布局：10x10，仅 A1-A5 / B1-B5 可部署，E4 已被芬占用
        assert gs.game_map.cols == 10 and len(gs.game_map.cells) == 100
        ab5 = {"%s%d" % (c, r) for c in ("A", "B") for r in range(1, 6)}
        ids = set(gs.game_map.deployable_ids())
        assert ids == ab5
        occupied = {c.cell_id for c in gs.game_map.cells if c.occupied}
        assert occupied == {"E4"}
        # 敌人从左侧来，含重装；计时估算
        assert gs.enemies_on_field
        assert all(e.position_hint == "左侧" for e in gs.enemies_on_field)
        heavy = [e for e in gs.enemies_on_field if e.name == "重装敌人"]
        assert heavy and heavy[0].observed_count == 3
        assert gs.timing_source == "estimated"
        assert any("估算值" in n for n in gs.notes)
        # 源石虫被标为 cv 确认，其余为 timer 估算
        src = {e.name: e.source for e in gs.enemies_on_field}
        assert src["源石虫"] == "cv"
        assert src["重装敌人"] == "timer:estimated"


class TestOCRCost:
    def test_roi_comes_from_config(self):
        from perception.ocr_cost import MockOCRCostReader
        r = MockOCRCostReader(value=15)
        assert r.roi == (1030, 24, 1112, 66)

    def test_mock_stable_reading_is_ok(self):
        import numpy as np
        from perception.ocr_cost import MockOCRCostReader
        r = MockOCRCostReader(value=15)
        frame = np.zeros((720, 1280, 3), dtype="uint8")
        a, b = r.read(frame), r.read(frame)
        assert (a.state, a.current, a.source) == ("ok", 15, "mock")
        assert b.state == "ok" and a.confidence == 1.0

    def test_two_frame_mismatch_is_uncertain(self):
        import numpy as np
        from perception.ocr_cost import MockOCRCostReader
        r = MockOCRCostReader(values=[15, 16])
        frame = np.zeros((720, 1280, 3), dtype="uint8")
        first = r.read(frame)
        second = r.read(frame)
        assert first.state == "ok" and first.current == 15
        assert second.state == "uncertain" and second.current == 16
        assert second.confidence <= 0.4       # 存疑时压低置信度
        # 下一帧重新一致即恢复 ok
        r3 = MockOCRCostReader(values=[15, 16, 16])
        r3.read(frame); r3.read(frame)
        assert r3.read(frame).state == "ok"

    def test_missing_does_not_update_memory(self):
        import numpy as np
        from perception.ocr_cost import MockOCRCostReader
        r = MockOCRCostReader(values=[None, 15])
        frame = np.zeros((720, 1280, 3), dtype="uint8")
        miss = r.read(frame)
        assert miss.state == "missing" and miss.current == 0
        ok = r.read(frame)                     # 上一稳定值仍为空，15 是首帧 -> ok
        assert ok.state == "ok" and ok.current == 15

    def test_reset_clears_last(self):
        from perception.ocr_cost import MockOCRCostReader
        r = MockOCRCostReader(values=[15, 16])
        r.reset()
        assert r._last is None

    def test_custom_roi_is_cropped(self):
        import numpy as np
        from perception.ocr_cost import BaseCostReader

        class Probe(BaseCostReader):
            reading_source = "mock"
            def _recognize_digit(self, crop):
                self.seen = crop.shape
                return 7, 1.0

        frame = np.zeros((720, 1280, 3), dtype="uint8")
        p = Probe(roi=(0, 0, 10, 12))
        out = p.read(frame)
        assert p.seen == (12, 10, 3) and out.current == 7 and out.state == "ok"

    def test_bad_roi_raises(self):
        import numpy as np
        from perception.ocr_cost import BaseCostReader, OCRError

        class P(BaseCostReader):
            reading_source = "mock"
            def _recognize_digit(self, crop):
                return 1, 1.0

        with pytest.raises(OCRError):
            P(roi=(0, 0, 0, 0)).read(np.zeros((720, 1280, 3), dtype="uint8"))

    def test_parse_number_picks_highest_score_digit(self):
        from perception.ocr_cost import OCRCostReader
        res = [[[[0, 0], [1, 1]], [("DP:15", 0.97), ("9", 0.5)]]]
        num, score = OCRCostReader._parse_number(res)
        assert num == 15 and abs(score - 0.97) < 1e-6
        assert OCRCostReader._parse_number([["无数字", 0.9]]) == (None, 0.0)

    def test_real_reader_requires_paddle(self):
        import importlib.util
        import numpy as np
        if importlib.util.find_spec("paddleocr") is not None:
            pytest.skip("已安装 paddleocr，跳过缺引擎用例")
        from perception.ocr_cost import OCRCostReader, OCRError
        r = OCRCostReader()
        with pytest.raises(OCRError):
            r._recognize_digit(np.zeros((42, 82, 3), dtype="uint8"))


class TestMapParser:
    def test_cell_roundtrip(self):
        from perception.map_parser import cell_to_colrow, default_deployable_ids
        assert cell_to_colrow("A1") == (0, 0)
        assert cell_to_colrow("B5") == (1, 4)
        assert cell_to_colrow("AA1") == (26, 0)
        assert default_deployable_ids() == \
            ["%s%d" % (c, r) for c in ("A", "B") for r in range(1, 6)]
        with pytest.raises(ValueError):
            cell_to_colrow("???")

    def test_mock_fixed_layout(self):
        from perception.map_parser import MockMapParser
        g = MockMapParser().parse(cache_key="3-8")
        assert g.cols == 10 and g.rows == 10 and len(g.cells) == 100
        ab5 = {"%s%d" % (c, r) for c in ("A", "B") for r in range(1, 6)}
        assert set(g.deployable_ids()) == ab5
        c3 = {c.cell_id: c for c in g.cells}["C3"]
        assert c3.terrain == "blocked" and not c3.deployable

    def test_layout_is_cached_per_key(self):
        from perception.map_parser import MockMapParser
        m = MockMapParser()
        a = m.parse(cache_key="3-8")
        b = m.parse(cache_key="3-8")
        assert a is b and m.has_cache("3-8")
        c = m.parse(cache_key="4-7")
        assert c is not a
        d = m.parse(cache_key="3-8", force=True)
        assert d is not a

    def test_occupied_and_writeback(self):
        from perception.map_parser import MockMapParser
        m = MockMapParser(occupied_ids=["A3"])
        g = m.parse()
        a3 = {c.cell_id: c for c in g.cells}["A3"]
        assert a3.occupied and a3.deployable
        assert "A3" not in g.deployable_ids() and "B1" in g.deployable_ids()
        g2 = m.set_occupied(["A3", "B2"])
        assert {c.cell_id for c in g2.cells if c.occupied} == {"A3", "B2"}

    def test_real_detect_not_implemented(self):
        from perception.map_parser import MapParser
        with pytest.raises(NotImplementedError):
            MapParser().parse(cache_key="never")


class TestYoloDetector:
    def test_config_roi_and_threshold(self):
        from perception.detector_yolo import YoloDetector
        d = YoloDetector()
        assert d.confirm_roi == (0, 300, 360, 620)
        assert d.weights == "weights/yolov8n_arknights.pt"
        assert 0 < d.conf_threshold < 1

    def test_real_detect_is_todo_v100(self):
        import numpy as np
        from perception.detector_yolo import YoloDetector
        with pytest.raises(NotImplementedError) as ei:
            YoloDetector().detect(np.zeros((720, 1280, 3), dtype="uint8"))
        assert "TODO-V100" in str(ei.value)
        with pytest.raises(NotImplementedError):
            YoloDetector().confirm_spawn("碎骨", np.zeros((720, 1280, 3), dtype="uint8"))

    def test_mock_detect_fixed_three_heavy_left(self):
        import numpy as np
        from perception.detector_yolo import MockDetector
        d = MockDetector()
        objs = d.detect(np.zeros((720, 1280, 3), dtype="uint8"))
        assert len(objs) == 3
        assert all(o.label == "重装敌人" and o.source == "mock" for o in objs)
        # bbox 全部落在左侧入场 ROI 内
        for o in objs:
            assert 0 <= o.bbox.x1 < o.bbox.x2 <= 360
            assert 300 <= o.bbox.y1 < o.bbox.y2 <= 620

    def test_mock_confirm_spawn(self):
        import numpy as np
        from perception.detector_yolo import MockDetector
        frame = np.zeros((720, 1280, 3), dtype="uint8")
        d = MockDetector()
        assert d.confirm_spawn("重装敌人", frame) is True
        assert d.confirm_spawn("碎骨", frame) is False
        assert d.confirm_spawn("", frame) is False

    def test_custom_roi_and_objects(self):
        import numpy as np
        from perception.detector_yolo import MockDetector
        d = MockDetector(objects=[("碎骨", 0.99, (0.0, 0.0, 1.0, 1.0))])
        objs = d.detect(frame=np.zeros((720, 1280, 3), dtype="uint8"),
                        roi=(100, 100, 200, 200))
        assert objs[0].label == "碎骨"
        assert (objs[0].bbox.x1, objs[0].bbox.y1, objs[0].bbox.x2, objs[0].bbox.y2) == \
            (100, 100, 200, 200)

    def test_confirmation_upgrades_spawn_tracker_to_cv(self):
        # 端到端：confirm_spawn 的布尔结果驱动 SpawnTracker estimated -> cv
        import numpy as np
        from perception.detector_yolo import MockDetector
        from perception.state_parser import SpawnTracker, StateParser
        cfg = {"spawn": {"default_spawn_interval_sec": 6.0, "timeline": {}}}
        tracker = SpawnTracker(config=cfg)
        stage = {"enemies": [{"名称": "重装敌人", "数量": 3}]}
        plan, _ = tracker.build_plan("3-8", stage)
        confirmed = MockDetector().confirm_spawn(
            "重装敌人", np.zeros((720, 1280, 3), dtype="uint8"))
        plan, presence = SpawnTracker.update(plan, 10.0, {"重装敌人": confirmed})
        assert presence[0].source == "cv" and plan[0].confirmed_by == "cv"
        # 未确认的敌人仍保持 estimated
        plan2, _ = tracker.build_plan("3-8", stage)
        plan2, presence2 = SpawnTracker.update(plan2, 10.0, {"重装敌人": False})
        assert presence2[0].source == "timer:estimated"
        # 用上文变量避免静态检查抱怨
        assert StateParser is not None


class TestVLMAnalysisSchema:
    def test_valid_analysis(self):
        from perception.schemas import EvidenceRef, VLMAnalysis
        a = VLMAnalysis(situation="s", strategic_advice="a", confidence=0.8,
                        evidence=[EvidenceRef(source="PRTS攻略", detail="重装弱法术",
                                              evidence="retrieved")])
        assert a.level == "inferred" and a.analyzer == "vlm"
        import json
        json.dumps(a.model_dump(), ensure_ascii=False)

    def test_confidence_bounds(self):
        from pydantic import ValidationError
        from perception.schemas import VLMAnalysis
        with pytest.raises(ValidationError):
            VLMAnalysis(confidence=1.5)


class TestVLMAnalyzer:
    def test_real_analyzer_is_todo_v100(self):
        from perception.vlm_analyzer import VLMAnalyzer
        from perception.state_parser import MockStateParser
        state = MockStateParser().get_state()
        with pytest.raises(NotImplementedError):
            VLMAnalyzer(model_name="").analyze(None, state)
        # 已加载模型后，缺帧应明确报错
        v = VLMAnalyzer(model_name="Qwen3-VL")
        v._model = object()
        with pytest.raises(ValueError):
            v.analyze(None, state)

    def test_mock_analysis_fields_and_evidence(self):
        from perception.vlm_analyzer import MockVLMAnalyzer, state_to_context
        from perception.state_parser import MockStateParser
        state = MockStateParser().get_state(elapsed_sec=12.0)
        a = MockVLMAnalyzer().analyze(None, state)
        assert a.analyzer == "mock" and a.level == "inferred"
        assert "费用15" in a.situation and "重装敌人" in a.situation
        assert "术师" in a.strategic_advice
        assert 0.0 <= a.confidence <= 1.0
        # 重装触发 retrieved 攻略引用
        refs = [(e.source, e.evidence) for e in a.evidence]
        assert ("PRTS攻略", "retrieved") in refs
        assert any("估算" in r for r in a.risks)
        ctx = state_to_context(state)
        assert '"stage_id":"3-8"' in ctx

    def test_throttle_due(self):
        from perception.vlm_analyzer import VLMAnalyzer
        v = VLMAnalyzer(interval_sec=2.0)
        assert v.due(now=10.0)
        v._last_run = 9.5
        assert not v.due(now=10.0)
        assert v.due(now=11.5)


class TestStateToText:
    def test_none_and_empty_state_safe(self):
        from perception.state_to_text import state_to_text
        from perception.schemas import GameState
        assert "暂无" in state_to_text(None)
        txt = state_to_text(GameState())
        for sec in ["【关卡】", "【资源】", "【可用干员】", "【敌情波次】", "【地图】",
                    "【证据分级】"]:
            assert sec in txt
        assert "无" in txt and "未知" in txt

    def test_full_report_sections_and_fields(self):
        from perception.state_to_text import state_to_text
        from perception.state_parser import MockStateParser
        from perception.vlm_analyzer import MockVLMAnalyzer
        state = MockStateParser().get_state(elapsed_sec=12.0)
        analysis = MockVLMAnalyzer().analyze(None, state)
        txt = state_to_text(state, analysis)
        # 资源
        assert "费用 15" in txt and "[稳定]" in txt and "耐久 3" in txt and "部署 1/9" in txt
        # 干员/职业/费用
        assert "翎羽(先锋,2费,可部署)" in txt
        assert "克洛丝(狙击,3费,可部署)" in txt
        # 已部署 + 技能
        assert "芬@E4朝左" in txt and "充能中" in txt
        # 敌情与来源标注
        assert "重装敌人 x3 [计时估算]" in txt
        assert "源石虫 x3 [CV确认]" in txt
        assert "波次构成:" in txt
        # 地图
        assert "10x10 可部署10格" in txt and "A1 A2 A3 A4 A5" in txt and "B5" in txt
        # VLM
        assert "【VLM局势】" in txt and "【VLM建议】" in txt and "术师" in txt
        # 估算备注透出
        assert "估算值" in txt

    def test_evidence_grades_present(self):
        from perception.state_to_text import state_to_text
        from perception.state_parser import MockStateParser
        from perception.vlm_analyzer import MockVLMAnalyzer
        state = MockStateParser().get_state()
        txt_no_vlm = state_to_text(state, None)
        assert "estimated(均匀估算值)" in txt_no_vlm
        assert "cv(视觉确认)" in txt_no_vlm
        analysis = MockVLMAnalyzer().analyze(None, state)
        txt = state_to_text(state, analysis)
        assert "retrieved(RAG参考资料,需核实)" in txt
        assert "inferred(规则/模型推断,非事实)" in txt
        assert "重装敌人防御高、弱法术" in txt

    def test_uncertain_cost_flagged(self):
        from perception.state_to_text import state_to_text
        from perception.schemas import CostStatus, GameState
        gs = GameState(cost=CostStatus(current=99, state="uncertain",
                                       confidence=0.3, source="cv"))
        txt = state_to_text(gs)
        assert "存疑" in txt and "暂勿据此决策" in txt

    def test_report_is_single_deterministic_string(self):
        from perception.state_to_text import state_to_text
        from perception.state_parser import MockStateParser
        a = state_to_text(MockStateParser().get_state())
        b = state_to_text(MockStateParser().get_state())
        # 时间戳来自 mock(time.time) 会变；去掉 t= 行后应一致
        norm = lambda s: "\n".join(l for l in s.splitlines() if not l.startswith("【关卡】"))
        assert norm(a) == norm(b)
