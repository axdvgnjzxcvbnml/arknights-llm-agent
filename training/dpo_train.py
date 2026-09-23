# -*- coding: utf-8 -*-
# TODO-V100: 偏好训练需要 V100 + CUDA。CPU 沙箱只保留偏好对读取/校验骨架，train() 显式报错。
"""DPO 偏好训练骨架（Direct Preference Optimization）。

偏好对来源（V100/真机阶段补充，当前不产出）：
- 同一对局状态下，Agent 的较差动作 vs 人工/慢思考的更优动作；
- 由决策日志（agent decision log）+ 人工标注整理为 {"prompt","chosen","rejected"}。

V100 上要补：
1. 在 SFT LoRA 权重（或基座）上初始化策略模型 + 参考模型（或 PEFT 免参考实现）；
2. trl.DPOTrainer / DPOTConfig，beta 见 configs/training.yaml（默认 0.1）；
3. fp16 训练并保存到 weights/dpo_qwen3_lora。
"""

import argparse
import json
import os

from .config import load_training_config

__all__ = ["load_preference_pairs", "train", "main"]


def load_preference_pairs(path):
    # type: (str) -> list
    """读取并校验偏好对 JSONL（纯 CPU）：每行需含 prompt/chosen/rejected。"""
    if not os.path.exists(path):
        raise FileNotFoundError("偏好对文件不存在：%s" % path)
    pairs = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for key in ("prompt", "chosen", "rejected"):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError("第 %d 行偏好对缺少/非法字段：%s" % (i, key))
            if row["chosen"].strip() == row["rejected"].strip():
                raise ValueError("第 %d 行 chosen 与 rejected 相同，无法构成偏好" % i)
            pairs.append(row)
    return pairs


def build_dpo_dataset(pairs, tokenizer, max_length, max_prompt_length):
    # TODO-V100: trl DPO 需要的 prompt/chosen/rejected 三列 tokenize。
    raise NotImplementedError(
        "TODO-V100: 在 V100 上 tokenize %d 条偏好对（max_length=%d）"
        % (len(pairs), max_length))


def train(cfg=None, pref_file=None, output_dir=None):
    # TODO-V100: DPO 训练循环（V100 + CUDA，可在 SFT LoRA 权重上继续偏好对齐）。
    cfg = cfg or load_training_config()
    dpo_cfg = cfg.get("dpo", {})
    pref_file = pref_file or os.path.join(
        "data/sft_data", dpo_cfg.get("pref_file", "dpo_pairs.jsonl"))
    pairs = load_preference_pairs(pref_file)
    raise NotImplementedError(
        "TODO-V100: DPO 训练尚未实现。已读取 %d 条偏好对(%s)。"
        "请在 V100 上用 trl.DPOTrainer(beta=%s, fp16, lr=%s) 训练并保存到 %s"
        % (len(pairs), pref_file, dpo_cfg.get("beta"),
           dpo_cfg.get("learning_rate"),
           output_dir or dpo_cfg.get("output_dir")))


def main(argv=None):
    ap = argparse.ArgumentParser(description="DPO 偏好训练（V100；当前为骨架）")
    ap.add_argument("--config", default=None)
    ap.add_argument("--pairs", default=None, help="偏好对 JSONL（默认 config dpo.pref_file）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    return train(load_training_config(args.config), pref_file=args.pairs,
                 output_dir=args.out)


if __name__ == "__main__":
    raise SystemExit(main())
