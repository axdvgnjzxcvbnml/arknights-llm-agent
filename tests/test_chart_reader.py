"""video_extract/chart_reader.py 单元测试。

覆盖：
- _strip_json_fence：剥离 markdown ```json fence（已知坑2）
- _validate_output：检测 VLM 照抄 prompt 示例字面量（已知坑1）
- VLMChartReader._load_model：无模型时抛 NotImplementedError(TODO-V100)
- read_chart：图片不存在时抛 ChartReadError
- MockChartReader：正常产出固定图表
"""
import json
import os
import tempfile

import pytest

from video_extract.chart_reader import (
    ChartReadError, ChartRecord, MockChartReader, VLMChartReader,
)


# ---------------- _strip_json_fence ----------------

class TestStripJsonFence(object):
    def test_fence_with_json_tag(self):
        text = '```json\n{"a": 1}\n```'
        assert VLMChartReader._strip_json_fence(text) == '{"a": 1}'

    def test_fence_without_tag(self):
        text = '```\n{"a": 1}\n```'
        assert VLMChartReader._strip_json_fence(text) == '{"a": 1}'

    def test_no_fence(self):
        text = '{"a": 1}'
        assert VLMChartReader._strip_json_fence(text) == '{"a": 1}'

    def test_empty_string(self):
        assert VLMChartReader._strip_json_fence("") == ""

    def test_none(self):
        assert VLMChartReader._strip_json_fence(None) is None

    def test_opening_fence_only(self):
        """只有开头 ```json 没有结尾 ``` 的情况。"""
        text = '```json\n{"a": 1}'
        assert VLMChartReader._strip_json_fence(text) == '{"a": 1}'

    def test_multiline_json(self):
        text = '```json\n{\n  "a": 1,\n  "b": [1, 2, 3]\n}\n```'
        result = VLMChartReader._strip_json_fence(text)
        assert json.loads(result) == {"a": 1, "b": [1, 2, 3]}


# ---------------- _validate_output ----------------

class TestValidateOutput(object):
    def test_normal_output_passes(self):
        parsed = {"chart_type": "table", "operator": "银灰",
                  "data": {"title": "危机合约DPS榜"}, "confidence": 0.9}
        result = VLMChartReader._validate_output(parsed)
        assert result["operator"] == "银灰"
        assert result["chart_type"] == "table"

    def test_operator_copies_example_literal(self):
        """VLM 照抄示例字面量 '主角干员名' → 被检测并丢弃。"""
        parsed = {"chart_type": "table", "operator": "主角干员名",
                  "data": {"title": "实际标题"}, "confidence": 0.9}
        result = VLMChartReader._validate_output(parsed)
        assert result["chart_type"] == "unknown"
        assert result["confidence"] == 0.0
        assert "_warning" in result

    def test_title_copies_example_literal(self):
        parsed = {"chart_type": "table", "operator": "银灰",
                  "data": {"title": "示例标题"}, "confidence": 0.9}
        result = VLMChartReader._validate_output(parsed)
        assert result["chart_type"] == "unknown"

    def test_non_dict_input(self):
        result = VLMChartReader._validate_output("not a dict")
        assert result["chart_type"] == "unknown"
        assert result["confidence"] == 0.0

    def test_all_example_literals_detected(self):
        for literal in VLMChartReader._EXAMPLE_LITERALS:
            parsed = {"chart_type": "table", "operator": literal,
                      "data": {}, "confidence": 0.9}
            result = VLMChartReader._validate_output(parsed)
            assert result["chart_type"] == "unknown", "应检测到示例字面量: %r" % literal


# ---------------- VLMChartReader 骨架 ----------------

class TestVLMChartReaderSkeleton(object):
    def test_no_model_raises_todo_v100(self):
        """未配置 model_name 时，_load_model 抛 NotImplementedError(TODO-V100)。"""
        reader = VLMChartReader(config={"vlm": {"model": "", "device": "cpu"}})
        with pytest.raises(NotImplementedError, match="TODO-V100"):
            reader._load_model()

    def test_read_chart_missing_frame_raises(self):
        """图片不存在时抛 ChartReadError（不触发模型加载）。"""
        reader = VLMChartReader(config={"vlm": {"model": "", "device": "cpu"}})
        with pytest.raises(ChartReadError, match="帧图片不存在"):
            reader.read_chart("/nonexistent/path.png", 12.5)

    def test_model_caching(self):
        """_load_model 有缓存机制（_model is not None 时直接返回）。"""
        reader = VLMChartReader(config={"vlm": {"model": "", "device": "cpu"}})
        assert reader._model is None
        assert reader._processor is None
        # 无 model_name 时抛错，但缓存字段仍为 None
        with pytest.raises(NotImplementedError):
            reader._load_model()
        assert reader._model is None


# ---------------- MockChartReader ----------------

class TestMockChartReader(object):
    def _make_frames(self):
        return [
            {"timestamp_sec": 5.0, "frame_path": "/tmp/f1.png"},
            {"timestamp_sec": 12.0, "frame_path": "/tmp/f2.png"},
            {"timestamp_sec": 21.0, "frame_path": "/tmp/f3.png"},
        ]

    def test_read_all_returns_two_charts(self):
        reader = MockChartReader()
        results = reader.read_all(self._make_frames())
        assert len(results) == 2
        assert results[0].chart_type == "table"
        assert results[1].chart_type == "tier_list"

    def test_chart_records_have_evidence(self):
        reader = MockChartReader()
        results = reader.read_all(self._make_frames())
        for r in results:
            assert r.evidence == "retrieved:video_frame"
            assert r.confidence > 0

    def test_empty_frames_returns_empty(self):
        reader = MockChartReader()
        assert reader.read_all([]) == []

    def test_write_output_json(self):
        reader = MockChartReader()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        try:
            results = reader.read_all(self._make_frames(), out_json=out_path)
            assert os.path.exists(out_path)
            with open(out_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data) == len(results)
            assert data[0]["chart_type"] == "table"
        finally:
            os.unlink(out_path)
