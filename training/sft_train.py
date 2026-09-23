# -*- coding: utf-8 -*-
# TODO-V100: 本文件的模型加载 / LoRA 配置 / 训练循环 / checkpoint 保存需要 V100 + CUDA。
# CPU 沙箱只保留可运行的"数据读取 + 参数打印"骨架；train() 在补齐实现前显式报错，不假装训练。
"""SFT 微调骨架：LoRA 微调 Qwen3-8B（慢思考模型）。

V100 上要补的实现（已在对应函数标注 TODO-V100）：
1. load_tokenizer/model：transformers AutoTokenizer/AutoModelForCausalLM，fp16(V100 无 bf16)；
2. build_lora_config：peft LoraConfig + get_peft_model（target_modules 见 configs/training.yaml）；
3. 把 sft_data_prep 产出的 question/answer 拼为 prompt+completion，tokenize 并 mask 掉 prompt 部分的 label；
4. transformers.Trainer（或手写循环）按 configs/training.yaml 超参训练；
5. checkpoint 保存到 weights/sft_qwen3_lora（gitignore）。
"""

import argparse
import json
import os

from .config import load_training_config

__all__ = ["load_jsonl", "build_prompt", "train", "main"]

PROMPT_TEMPLATE = (
    "你是明日方舟 AI 代理。请根据当前对局状态给出下一步动作与理由，"
    "动作词表 deploy/skill/retreat/wait。\n\n{question}\n")


def load_jsonl(path):
    # type: (str) -> list
    """读取 sft_data_prep 产出的 JSONL（纯 CPU）。"""
    if not os.path.exists(path):
        raise FileNotFoundError("SFT 数据不存在：%s（先运行 training.sft_data_prep）" % path)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "question" not in row or "answer" not in row:
                raise ValueError("第 %d 行缺少 question/answer 字段" % i)
            rows.append(row)
    return rows


def build_prompt(question):
    # type: (str) -> str
    return PROMPT_TEMPLATE.format(question=question.strip())


def load_tokenizer_and_model(model_name, dtype, trust_remote_code):
    # TODO-V100: transformers AutoTokenizer/AutoModelForCausalLM；V100(sm_70) 用 float16。
    raise NotImplementedError(
        "TODO-V100: 在 V100 上用 transformers 加载 %s（fp16），并 to('cuda')" % model_name)


def build_lora_config(lora_cfg):
    # TODO-V100: from peft import LoraConfig, get_peft_model；按 configs/training.yaml 注入。
    raise NotImplementedError(
        "TODO-V100: 用 peft.LoraConfig(r=%s,alpha=%s) 包装模型"
        % (lora_cfg.get("r"), lora_cfg.get("lora_alpha")))


def tokenize_dataset(rows, tokenizer, max_length):
    # TODO-V100: prompt 部分 label 置 -100，仅对 answer 计算 loss；padding/truncation。
    raise NotImplementedError(
        "TODO-V100: 在 V100 上把 %d 条 question/answer tokenize（max_length=%d）"
        % (len(rows), max_length))


def train(cfg=None, train_file=None, eval_file=None, output_dir=None):
    # TODO-V100: 完整 LoRA SFT 训练循环（V100 + CUDA，预计单卡 16G，batch1 x grad_accum16）。
    cfg = cfg or load_training_config()
    sft_cfg = cfg.get("sft", {})
    data_dir = sft_cfg.get("data_dir", "data/sft_data")
    train_file = train_file or os.path.join(
        data_dir, sft_cfg.get("train_file", "sft_train.jsonl"))
    # CPU 侧可做的真实动作：把数据读进来并自检
    rows = load_jsonl(train_file)
    raise NotImplementedError(
        "TODO-V100: LoRA SFT 训练尚未实现。已读取 %d 条样本(%s)。"
        "请在 V100 上补齐 load_tokenizer_and_model/build_lora_config/tokenize_dataset/"
        "Trainer，并按 configs/training.yaml(fp16/lr=%s/epochs=%s) 训练后保存到 %s"
        % (len(rows), train_file, sft_cfg.get("learning_rate"),
           sft_cfg.get("num_train_epochs"),
           output_dir or sft_cfg.get("output_dir")))


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT LoRA 微调（V100；当前为骨架）")
    ap.add_argument("--config", default=None)
    ap.add_argument("--train", default=None, help="训练 JSONL（默认 config sft.train_file）")
    ap.add_argument("--eval", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    cfg = load_training_config(args.config)
    return train(cfg, train_file=args.train, eval_file=args.eval,
                 output_dir=args.out)


if __name__ == "__main__":
    raise SystemExit(main())
