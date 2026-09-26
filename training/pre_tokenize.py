"""SFT 数据预 tokenize：把 sft_train.jsonl / sft_eval.jsonl 预处理为 input_ids + labels 格式。

V100 上线后训练的第一步是 tokenize 18080 条数据。CPU 侧提前做完省 V100 时间。

真实 tokenizer：Qwen/Qwen3-8B（trust_remote_code=True）。
沙箱无法下载时自动降级为 MockTokenizer（字符级分词），仅验证流程正确性，
token 统计不代表真实值，V100 上需用真实 tokenizer 重新跑。

SFT 标签格式：
- input_ids = tokenize(question + answer)
- labels = [-100] * len(question_ids) + answer_ids  （question 部分不计算 loss）
- 末尾加 eos_token_id

输出格式：JSONL，每条 {"input_ids": [...], "labels": [...], "meta": {...}}
V100 上可用 datasets.load_dataset("json", data_files=...) 直接加载。

用法：
    python -m training.pre_tokenize                # 预处理 train + eval
    python -m training.pre_tokenize --split train  # 只预处理 train
    python -m training.pre_tokenize --stats-only   # 只统计，不写文件
"""

import argparse
import json
import os
import time
from typing import List, Optional, Tuple

from .config import load_training_config

__all__ = ["load_tokenizer", "MockTokenizer", "pre_tokenize_file", "pre_tokenize_all"]

# TODO-V100: 沙箱无法下载 Qwen3-8B tokenizer，V100 上用真实 tokenizer 替换 MockTokenizer。
# 真实加载：AutoTokenizer.from_pretrained("Qwen/Qwen3-8B", trust_remote_code=True)


class MockTokenizer:
    """沙箱降级用的 mock tokenizer：字符级分词，仅验证流程正确性。

    分词规则：
    - 中文字符：每个字一个 token
    - 英文/数字：连续字母数字一个 token
    - 标点/空白：每个字符一个 token
    - vocab_size 固定为 65536（模拟），eos_token_id=151643（Qwen3 真实 eos）

    注意：mock 的 token 数与真实 Qwen3 tokenizer 差异很大，仅用于流程验证。
    """

    def __init__(self):
        self.vocab_size = 65536
        self.eos_token_id = 151643
        self.bos_token_id = 151643  # Qwen3 无独立 bos，用 eos 占位

    def encode(self, text: str) -> List[int]:
        """字符级分词：中文逐字、英文连续、标点逐字。hash 到 0..vocab_size-2。"""
        tokens = []
        buf = ""
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                if buf:
                    tokens.append(hash(buf) % (self.vocab_size - 2) + 10)
                    buf = ""
                tokens.append(hash(ch) % (self.vocab_size - 2) + 10)
            elif ch.isalnum():
                buf += ch
            else:
                if buf:
                    tokens.append(hash(buf) % (self.vocab_size - 2) + 10)
                    buf = ""
                tokens.append(hash(ch) % (self.vocab_size - 2) + 10)
        if buf:
            tokens.append(hash(buf) % (self.vocab_size - 2) + 10)
        return tokens

    def decode(self, ids: List[int]) -> str:
        """mock decode 不还原原文，返回占位字符串。"""
        return "<mock-decoded-%d-tokens>" % len(ids)


def load_tokenizer(model_name: str = "Qwen/Qwen3-8B"):
    """尝试加载真实 tokenizer，失败则降级为 MockTokenizer。

    :return: (tokenizer, is_mock)
    """
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True, timeout=20)
        return tok, False
    except Exception as e:
        print("[pre_tokenize] 真实 tokenizer 加载失败（%s），降级为 MockTokenizer"
              % type(e).__name__)
        print("[pre_tokenize] # TODO-V100: V100 上用 Qwen/Qwen3-8B 真实 tokenizer 重新跑")
        return MockTokenizer(), True


def _build_sft_pair(question: str, answer: str, tokenizer,
                     max_length: int = 2048) -> Tuple[List[int], List[int]]:
    """构造 SFT 训练样本：input_ids + labels（question 部分 labels=-100）。

    格式：[question_tokens] + [answer_tokens] + [eos]
    labels：[-100]*len(question) + answer_tokens + [eos]
    超过 max_length 截断（从尾部截断，保留 question 前缀）。
    """
    q_ids = tokenizer.encode(question)
    a_ids = tokenizer.encode(answer)
    eos_id = getattr(tokenizer, "eos_token_id", 151643)

    # 截断：总长度不超过 max_length，优先保留 question
    if len(q_ids) + len(a_ids) + 1 > max_length:
        budget = max_length - len(a_ids) - 1
        if budget < 64:  # question 至少保留 64 token
            budget = 64
            a_ids = a_ids[:max_length - budget - 1]
        q_ids = q_ids[:budget]

    input_ids = q_ids + a_ids + [eos_id]
    labels = [-100] * len(q_ids) + a_ids + [eos_id]
    return input_ids, labels


def pre_tokenize_file(input_path: str, output_path: str, tokenizer,
                      max_length: int = 2048, stats_only: bool = False) -> dict:
    """预 tokenize 单个 JSONL 文件。

    :return: 统计 dict {total, total_tokens, avg_length, max_length, min_length, skipped}
    """
    if not os.path.exists(input_path):
        print("[pre_tokenize] 输入文件不存在: %s" % input_path)
        return {"total": 0, "total_tokens": 0, "avg_length": 0,
                "max_length": 0, "min_length": 0, "skipped": 0}

    total = 0
    total_tokens = 0
    max_len = 0
    min_len = 10 ** 9
    skipped = 0
    out_f = None if stats_only else open(output_path, "w", encoding="utf-8")

    t0 = time.time()
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    example = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue

                question = example.get("question", "")
                answer = example.get("answer", "")
                meta = example.get("meta", {})

                if not question or not answer:
                    skipped += 1
                    continue

                input_ids, labels = _build_sft_pair(question, answer, tokenizer, max_length)
                total += 1
                total_tokens += len(input_ids)
                max_len = max(max_len, len(input_ids))
                min_len = min(min_len, len(input_ids))

                if out_f is not None:
                    out_f.write(json.dumps({
                        "input_ids": input_ids,
                        "labels": labels,
                        "meta": meta,
                    }, ensure_ascii=False) + "\n")

                if total % 2000 == 0:
                    elapsed = time.time() - t0
                    print("[pre_tokenize]   已处理 %d 条，平均 %.1f token/条，耗时 %.1fs"
                          % (total, total_tokens / total, elapsed))
    finally:
        if out_f is not None:
            out_f.close()

    stats = {
        "total": total,
        "total_tokens": total_tokens,
        "avg_length": round(total_tokens / total, 1) if total else 0,
        "max_length": max_len,
        "min_length": min_len if total else 0,
        "skipped": skipped,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    return stats


def pre_tokenize_all(config_path: Optional[str] = None, split: str = "all",
                      stats_only: bool = False) -> dict:
    """预 tokenize train + eval（或指定 split）。

    :param split: "all" | "train" | "eval"
    :return: {"train": stats, "eval": stats, "tokenizer": str, "is_mock": bool}
    """
    cfg = load_training_config(config_path)
    data_cfg = cfg.get("data", {})
    data_dir = data_cfg.get("data_dir", "data/sft_data")
    train_file = data_cfg.get("train_file", "sft_train.jsonl")
    eval_file = data_cfg.get("eval_file", "sft_eval.jsonl")
    max_length = int(data_cfg.get("max_length", 2048))
    model_name = cfg.get("model", {}).get("name", "Qwen/Qwen3-8B")

    tokenizer, is_mock = load_tokenizer(model_name)
    tok_name = "MockTokenizer(字符级)" if is_mock else model_name
    print("[pre_tokenize] tokenizer: %s (is_mock=%s)" % (tok_name, is_mock))
    print("[pre_tokenize] max_length: %d" % max_length)

    result = {"tokenizer": tok_name, "is_mock": is_mock, "max_length": max_length}

    if split in ("all", "train"):
        in_path = os.path.join(data_dir, train_file)
        out_path = os.path.join(data_dir, train_file.replace(".jsonl", "_tokenized.jsonl"))
        print("[pre_tokenize] 处理 train: %s -> %s" % (in_path, out_path))
        result["train"] = pre_tokenize_file(in_path, out_path, tokenizer, max_length, stats_only)
        print("[pre_tokenize] train 统计: %s" % result["train"])

    if split in ("all", "eval"):
        in_path = os.path.join(data_dir, eval_file)
        out_path = os.path.join(data_dir, eval_file.replace(".jsonl", "_tokenized.jsonl"))
        print("[pre_tokenize] 处理 eval: %s -> %s" % (in_path, out_path))
        result["eval"] = pre_tokenize_file(in_path, out_path, tokenizer, max_length, stats_only)
        print("[pre_tokenize] eval 统计: %s" % result["eval"])

    # 写统计文件
    if not stats_only:
        stats_path = os.path.join(data_dir, "pretokenize_stats.json")
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("[pre_tokenize] 统计已写入 %s" % stats_path)

    if is_mock:
        print("[pre_tokenize] 警告：当前使用 MockTokenizer，token 统计不代表真实值。"
              "V100 上需用 Qwen/Qwen3-8B 真实 tokenizer 重新跑。")

    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="SFT 数据预 tokenize")
    parser.add_argument("--config", default=None, help="training config 路径")
    parser.add_argument("--split", default="all", choices=["all", "train", "eval"],
                        help="预处理哪个 split（默认 all）")
    parser.add_argument("--stats-only", action="store_true",
                        help="只统计 token 分布，不写 tokenized 文件")
    args = parser.parse_args(argv)

    result = pre_tokenize_all(config_path=args.config, split=args.split,
                               stats_only=args.stats_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
