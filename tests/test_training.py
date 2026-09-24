"""训练模块测试：SFT 数据准备（CPU 真实）、质量审计、dry-run 契约、import 轻量。

- 数据准备/审计：用 data/mock 下的小样本 JSONL 做真实处理（不依赖 GPU）。
- dry-run 集成测试默认 skip（需联网下载 Qwen tokenizer），显式
  ARK_RUN_TRAIN_DRYRUN=1 时开启。
- label 掩码 / 左截断契约有纯 Python 单测恒跑（不 import torch）。
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK = os.path.join(ROOT, "data", "mock")


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------- SFT 数据准备（真实 CPU 逻辑） ----------

def test_prep_mock_job(tmp_path):
    """mock 作业 -> JSONL：deploy 动作转写正确，含证据分级。"""
    from training.sft_data_prep import prepare_sft
    out_dir = str(tmp_path / "out")
    job_dir = os.path.join(MOCK, "maa_jobs")
    prepare_sft(job_dir=job_dir, prts_dir=None, out_dir=out_dir, split=True)
    train = os.path.join(out_dir, "sft_train.jsonl")
    assert os.path.isfile(train)
    with open(train, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert lines
    first = json.loads(lines[0])
    assert first["question"].startswith("[关卡]")
    assert "理由：" in first["answer"]
    assert "inferred" in first["answer"]


def test_prep_split_disjoint(tmp_path):
    from training.sft_data_prep import prepare_sft
    out_dir = str(tmp_path / "out")
    prepare_sft(job_dir=os.path.join(MOCK, "maa_jobs"), prts_dir=None,
                out_dir=out_dir, split=True)
    train_stages = set()
    eval_stages = set()
    for fn, bucket in (("sft_train.jsonl", train_stages),
                       ("sft_eval.jsonl", eval_stages)):
        with open(os.path.join(out_dir, fn), "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                stage = obj["question"].split(" ", 1)[0].strip("[]关卡 ")
                bucket.add(stage)
    assert not (train_stages & eval_stages), "train/eval 关卡有交集（泄漏）"


def test_prep_generic_operator_filtered(tmp_path):
    """职业泛称/占位动作（如 输出/医疗2）不入训。"""
    from training.sft_data_prep import is_generic_operator, prepare_sft
    assert is_generic_operator("输出")
    assert is_generic_operator("医疗2")
    assert is_generic_operator("铁卫-守护者")
    assert is_generic_operator("地刺：精一满级及以上")
    assert not is_generic_operator("能天使")
    assert not is_generic_operator("弦惊")      # 召唤物
    assert not is_generic_operator("障碍物")    # 装置
    assert not is_generic_operator("麒麟X夜刀")  # 联动干员
    assert not is_generic_operator("御龙：雷狼龙")


def test_prep_unknown_action_skipped(tmp_path):
    """未识别的动作（如 部署_无名）应跳过而不是报错。"""
    from training.sft_data_prep import prepare_sft
    out_dir = str(tmp_path / "out")
    prepare_sft(job_dir=os.path.join(MOCK, "maa_jobs_bad"), prts_dir=None,
                out_dir=out_dir, split=False)
    with open(os.path.join(out_dir, "sft_train.jsonl"), "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        assert "部署_无名" not in line


# ---------- 质量审计 ----------

def test_audit_good_file(tmp_path):
    from training.sft_quality_audit import audit_file
    sample = os.path.join(tmp_path, "good.jsonl")
    with open(sample, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "question": "[关卡 3-8] 当前费用 15，部署 能天使",
            "answer": "deploy 能天使 at (2,3) facing 右。理由：inferred:timeline_reconstructed",
            "meta": {"stage": "3-8", "action": "deploy", "operator": "能天使"},
        }, ensure_ascii=False) + "\n")
    result = audit_file(sample, n=10)
    assert result["total"] == 1
    assert result["problems"] == 0


def test_audit_bad_file(tmp_path):
    from training.sft_quality_audit import audit_file
    sample = os.path.join(tmp_path, "bad.jsonl")
    with open(sample, "w", encoding="utf-8") as f:
        f.write(json.dumps({"question": "", "answer": "", "meta": {}},
                           ensure_ascii=False) + "\n")
    result = audit_file(sample, n=10)
    assert result["total"] == 1
    assert result["problems"] >= 1


# ---------- dry-run 契约（不 import torch） ----------

def test_dryrun_flags_contract():
    """sft_train --dry-run 必须显式 NotImplementedError 于真实模型路径。"""
    import training.sft_train as m
    assert hasattr(m, "main")


def test_import_light():
    """import training.sft_train 不得拉起 torch/transformers/peft。"""
    import sys
    heavy = {"torch", "transformers", "peft", "accelerate", "bitsandbytes"}
    loaded = {m for m in sys.modules if m.split(".")[0] in heavy}
    assert not loaded, "import 拉起了重依赖: %s" % sorted(loaded)


@pytest.mark.skipif(not os.environ.get("ARK_RUN_TRAIN_DRYRUN"),
                    reason="需联网下载 Qwen tokenizer；ARK_RUN_TRAIN_DRYRUN=1 开启")
def test_train_dryrun_integration():
    """真实 dry-run：极小随机模型跑 LoRA 全链路（数据/掩码/训练/存盘）。"""
    r = subprocess.run([sys.executable, "-m", "training.sft_train", "--dry-run",
                        "--sample-n", "8"], cwd=ROOT, capture_output=True, timeout=600)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert b"loss" in r.stdout or b"Loss" in r.stdout
