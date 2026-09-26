"""审计 M7：损坏 JSON 文件应被记录并跳过，不让整库/整图构建崩溃。

覆盖：
- knowledge/graph/build_graph._load_json_safe
- training/sft_data_prep.build_prts_index
均为纯 CPU、不依赖真实语料。
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from knowledge.graph import build_graph  # noqa: E402
from training import sft_data_prep  # noqa: E402


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_json_safe_skips_corrupt(tmp_path, capsys):
    _write(tmp_path / "operators" / "good.json",
            json.dumps({"name": "能天使"}, ensure_ascii=False))
    _write(tmp_path / "operators" / "bad.json", "{这不是合法 JSON")
    _write(tmp_path / "operators" / "empty.json", "")

    items = build_graph._load_json_safe(str(tmp_path), "operators", "干员")
    assert [stem for stem, _ in items] == ["good"]
    out = capsys.readouterr().out
    assert "bad" in out  # 坏文件被记录


def test_build_prts_index_skips_corrupt(tmp_path):
    stages = tmp_path / "stages"
    ops = tmp_path / "operators"
    _write(stages / "s_good.json", json.dumps({"code": "3-8"}, ensure_ascii=False))
    _write(stages / "s_bad.json", "{broken")
    _write(ops / "o_good.json", json.dumps({"name": "克洛丝"}, ensure_ascii=False))
    _write(ops / "o_bad.json", "{broken")

    stage_by_code, op_by_name = sft_data_prep.build_prts_index(str(tmp_path))
    assert list(stage_by_code) == ["3-8"]
    assert list(op_by_name) == ["克洛丝"]


def test_build_prts_index_missing_dir(tmp_path):
    stage_by_code, op_by_name = sft_data_prep.build_prts_index(str(tmp_path / "nope"))
    assert stage_by_code == {} and op_by_name == {}
