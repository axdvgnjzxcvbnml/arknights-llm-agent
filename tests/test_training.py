# -*- coding: utf-8 -*-
"""training 包单元测试：SFT 数据准备(CPU真实) + SFT/DPO 骨架(TODO-V100)。纯 CPU 恒跑。"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from training import sft_data_prep as prep  # noqa: E402
from training import sft_train, dpo_train  # noqa: E402

MOCK_JOB = os.path.join("data", "mock", "maa_job_3-8.json")
HAS_PRTS = os.path.isdir(os.path.join("data", "prts_raw", "stages"))


def _job(stage="t-1", actions=None, extra=None):
    d = {"stage_name": stage, "title": "t",
         "details": {"actions": actions if actions is not None else []}}
    if extra:
        d.update(extra)
    return d


# ---------------------------------------------------------------- 作业校验
class TestJobValidation:
    def test_load_sample_job(self):
        job = prep.load_maa_job(MOCK_JOB)
        assert job["stage_name"] == "3-8"
        assert len(job["details"]["actions"]) == 8

    def test_missing_stage(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"details": {"actions": [{"type": "部署"}]}}),
                     encoding="utf-8")
        with pytest.raises(ValueError):
            prep.load_maa_job(str(p))

    def test_missing_actions(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"stage_name": "x", "details": {}}), encoding="utf-8")
        with pytest.raises(ValueError):
            prep.load_maa_job(str(p))


# ---------------------------------------------------------------- 样本构造
class TestBuildExamples:
    def test_degraded_without_prts(self, tmp_path):
        # 无 PRTS 也必须能产出（CI fresh clone 场景）
        job = prep.load_maa_job(MOCK_JOB)
        ex, skipped = prep.build_examples(job, prts_dir=str(tmp_path))
        assert len(ex) == 8 and skipped == {}
        for r in ex:
            assert r["question"] and r["answer"]
            assert {"question", "answer", "meta"} <= set(r)
            ev = r["meta"]["evidence"]
            assert ev["action"] == "fact:maa_job"
            assert ev["rationale"].startswith("inferred:")
            assert "operator" not in ev and "enemies" not in ev
        assert "无 PRTS 语料" in ex[0]["question"]

    def test_action_mapping_and_prefix_state(self, tmp_path):
        job = prep.load_maa_job(MOCK_JOB)
        ex, _ = prep.build_examples(job, prts_dir=str(tmp_path))
        seq = [r["meta"]["action"] for r in ex]
        assert seq[0] == "deploy" and "skill" in seq and "retreat" in seq
        # 第 5 条(12F 部署)之前已部署 芬/安德切尔/安赛尔（从前缀时间轴反推）
        assert "芬" in ex[4]["question"] and "安德切尔" in ex[4]["question"]
        # answer 动作头与理由
        assert ex[0]["answer"].splitlines()[0].startswith("deploy 芬")
        assert "理由" in ex[0]["answer"]

    def test_unknown_action_skipped(self, tmp_path):
        job = _job(actions=[
            {"type": "部署", "name": "a", "location": [1, 1], "direction": "左", "kills": 0},
            {"type": "快速战斗", "kills": 1},
        ])
        ex, skipped = prep.build_examples(job, prts_dir=str(tmp_path))
        assert len(ex) == 1
        assert skipped.get("快速战斗") == 1

    @pytest.mark.skipif(not HAS_PRTS, reason="需要本地 PRTS 语料（fresh clone 无）")
    def test_with_real_prts_evidence(self):
        job = prep.load_maa_job(MOCK_JOB)
        ex, _ = prep.build_examples(job, prts_dir="data/prts_raw")
        ev0 = ex[0]["meta"]["evidence"]
        assert ev0["operator"] == "fact:prts" and ev0["enemies"] == "fact:prts"
        # 12F 术师理由引用高防敌人（拳刃武士防300/碎骨防240）
        caster = next(r for r in ex if r["meta"]["operator"] == "12F")
        assert "拳刃武士" in caster["answer"]
        assert "3-8 黄昏" in ex[0]["question"]


# ---------------------------------------------------------------- 落盘/切分
class TestPrepare:
    def test_write_and_split(self):
        out = os.path.join("data", "sft_data", "_ut_sft.jsonl")
        stats = prep.prepare_jobs([MOCK_JOB], out, prts_dir="/nonexistent_prts",
                                  eval_ratio=0.25)
        try:
            assert stats["n_all"] == 8
            assert os.path.exists(stats["train"]) and os.path.exists(stats["eval"])
            ntr = sum(1 for _ in open(stats["train"], encoding="utf-8"))
            nev = sum(1 for _ in open(stats["eval"], encoding="utf-8"))
            assert ntr + nev == 8 and nev >= 1
            row = json.loads(open(out, encoding="utf-8").readline())
            assert "question" in row and "answer" in row
        finally:
            for p in (out, stats["train"], stats["eval"]):
                if p and os.path.exists(p):
                    os.remove(p)


# ---------------------------------------------------------------- 训练骨架
class TestTrainSkeletons:
    def test_sft_loader_and_prompt(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text(json.dumps({"question": "状态X", "answer": "deploy a"},
                                ensure_ascii=False) + "\n", encoding="utf-8")
        rows = sft_train.load_jsonl(str(p))
        assert len(rows) == 1 and "状态X" in sft_train.build_prompt("状态X")

    def test_sft_train_is_todo_v100(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text(json.dumps({"question": "q", "answer": "a"}) + "\n",
                     encoding="utf-8")
        with pytest.raises(NotImplementedError) as ei:
            sft_train.train(train_file=str(p))
        assert "TODO-V100" in str(ei.value)

    def test_sft_missing_data(self):
        with pytest.raises(FileNotFoundError):
            sft_train.load_jsonl("/no/such/file.jsonl")

    def test_encode_masks_prompt_and_keeps_answer(self):
        # 纯 Python 假 tokenizer（不依赖 torch/网络），锁定 label 掩码与左截断契约
        class FakeTok(object):
            eos_token_id = 99

            def __call__(self, text, add_special_tokens=False):
                return {"input_ids": [ord(c) % 1000 + 1 for c in text]}

        row = {"question": "状态XYZ", "answer": "deploy a at 1"}
        enc = sft_train.encode_example(row, FakeTok(), max_length=500)
        prompt_ids = FakeTok()(sft_train.build_prompt("状态XYZ"))["input_ids"]
        n_p = len(prompt_ids)
        labels = enc["labels"]
        assert enc["input_ids"][:n_p] == prompt_ids          # 前段确为 prompt
        assert all(x == -100 for x in labels[:n_p])          # prompt 不计 loss
        assert labels[n_p] != -100 and labels[-1] == 99      # answer 计 loss，末尾 EOS

        # 超长：从 prompt 左侧截断，answer+EOS 必须完整保留
        small = sft_train.encode_example(row, FakeTok(), max_length=20)
        ans_ids = FakeTok()("deploy a at 1")["input_ids"] + [99]
        assert small["input_ids"][-len(ans_ids):] == ans_ids
        assert all(x != -100 for x in small["labels"][-len(ans_ids):])

    @pytest.mark.skipif(os.environ.get("ARK_RUN_TRAIN_DRYRUN") != "1",
                        reason="需联网下载 Qwen tokenizer + torch/peft；默认跳过，"
                               "设 ARK_RUN_TRAIN_DRYRUN=1 显式开启")
    def test_dry_run_pipeline_cpu(self, tmp_path):
        p = tmp_path / "tiny_train.jsonl"
        rows = [json.dumps({"question": "当前费用10，可部署先锋",
                            "answer": "deploy vanguard at (1,1) facing 右"},
                           ensure_ascii=False) for _ in range(4)]
        p.write_text("\n".join(rows) + "\n", encoding="utf-8")
        out = tmp_path / "adapter"
        m = sft_train.train(dry_run=True, train_file=str(p), output_dir=str(out),
                            max_samples=4, max_steps=1, max_length=128)
        assert m["optimizer_steps"] == 1 and m["loss_last"] is not None
        assert m["adapter_reload"] == "ok" and os.path.isdir(str(out))

    def test_dpo_loader_validation(self, tmp_path):
        good = tmp_path / "p.jsonl"
        good.write_text(json.dumps(
            {"prompt": "p", "chosen": "好动作", "rejected": "差动作"},
            ensure_ascii=False) + "\n", encoding="utf-8")
        assert len(dpo_train.load_preference_pairs(str(good))) == 1

        same = tmp_path / "same.jsonl"
        same.write_text(json.dumps({"prompt": "p", "chosen": "x", "rejected": "x"})
                        + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            dpo_train.load_preference_pairs(str(same))

    def test_dpo_train_is_todo_v100(self, tmp_path):
        p = tmp_path / "p.jsonl"
        p.write_text(json.dumps({"prompt": "p", "chosen": "c", "rejected": "r"})
                     + "\n", encoding="utf-8")
        with pytest.raises(NotImplementedError) as ei:
            dpo_train.train(pref_file=str(p))
        assert "TODO-V100" in str(ei.value)


class TestImportIsLight:
    def test_no_gpu_stack(self):
        code = ("import sys;"
                "import training, training.sft_data_prep, training.sft_train, training.dpo_train;"
                "b=['torch','transformers','peft','trl','numpy'];"
                "print('HEAVY:'+','.join(m for m in b if m in sys.modules))")
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.split("HEAVY:", 1)[1].strip() == ""
