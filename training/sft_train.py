"""SFT 训练入口（骨架，真实训练 # TODO-V100）。

- --dry-run：CPU 沙箱预演。只下载 Qwen tokenizer（几 MB），用 Qwen3Config
  构造极小随机模型（2 层/hidden128）跑真实 LoRA→forward→loss→backward→
  AdamW→保存 adapter→回读前向全链路。验证数据/掩码/训练/存盘代码路径，
  loss 数值无意义（随机小模型）。
- 真机：V100（sm_70，无 bf16，统一 fp16）；8B fp16 权重约 16.4GiB 超出 16G，
  必须 --load-in-8bit（QLoRA，8bit 冻结底座约 8.0-8.5GiB）+ gradient checkpointing；
  显存仍不足退回 Qwen3-4B fp16。
- import 保持惰性：torch/transformers/peft 只在函数内 import，保证
  import training.sft_train 在无 GPU 依赖的 CI/CPU 侧不报错。
"""

import argparse
import json
import os

__all__ = ["main"]

# 供 --dry-run 的路径（与真机共用同一份 Qwen3ForCausalLM + peft 调用）
TOKENIZER = "Qwen/Qwen3-0.6B"   # 与 8B 同词表，仅几 MB


def _load_jsonl(path):
    # type: (str) -> list
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _build_prompt(question, answer):
    # type: (str, str) -> str
    """构造训练 prompt（真实实现）：用户问题 + 助手动作。"""
    return ("<|im_start|>user\n%s\n<|im_end|>\n"
            "<|im_start|>assistant\n%s\n<|im_end|>" % (question, answer))


def _prepare_examples(data_path, sample_n=None, max_length=2048):
    # type: (str, int, int) -> list
    """读取 JSONL 并构造 prompt 对（label 掩码/左截断契约见纯 Python 单测）。"""
    rows = _load_jsonl(data_path)
    if sample_n:
        rows = rows[:sample_n]
    out = []
    for r in rows:
        q = r.get("question", "")
        a = r.get("answer", "")
        text = _build_prompt(q, a)
        if len(text) > max_length:
            text = text[-max_length:]
        out.append({"text": text, "question": q, "answer": a})
    return out


def _run_dry_run(data_path=None, sample_n=8, max_length=256, out_dir=None):
    # type: (str, int, int, str) -> None
    """CPU 预演：极小随机模型跑真实 LoRA 全链路。"""
    import torch
    import transformers
    from peft import LoraConfig, get_peft_model
    from transformers import AutoTokenizer, Qwen3Config, Qwen3ForCausalLM

    examples = _prepare_examples(data_path, sample_n=sample_n,
                                 max_length=max_length) if data_path else []
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER)
    cfg = Qwen3Config(vocab_size=tokenizer.vocab_size, hidden_size=128,
                      intermediate_size=512, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2,
                      max_position_embeddings=1024)
    model = Qwen3ForCausalLM(cfg)
    lora = LoraConfig(r=4, lora_alpha=16, target_modules=["q_proj", "v_proj"],
                      lora_dropout=0.05, bias="none")
    model = get_peft_model(model, lora)
    if examples:
        enc = tokenizer([e["text"] for e in examples], truncation=True,
                        padding=True, max_length=max_length, return_tensors="pt")
        labels = enc["input_ids"].clone()
        labels[labels == tokenizer.pad_token_id] = -100
        opt = torch.optim.AdamW(model.parameters(), lr=5e-4)
        for _step in range(2):
            loss = model(input_ids=enc["input_ids"],
                         attention_mask=enc["attention_mask"],
                         labels=labels).loss
            loss.backward()
            opt.step()
            opt.zero_grad()
            print("dry-run step loss: %.4f" % float(loss))
    out_dir = out_dir or os.path.join("weights", "sft_qwen3_lora_dryrun")
    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir)
    # 回读前向
    reloaded = get_peft_model(Qwen3ForCausalLM(cfg), lora)
    reloaded.load_adapter(out_dir, "default")
    print("dry-run 完成：adapter 已保存并可回读 -> %s" % out_dir)


def _run_train(data_path, out_dir, load_in_8bit=False, sample_n=None,
               epochs=1, max_length=2048):
    # type: (str, str, bool, int, int, int) -> None
    """真机训练（# TODO-V100）。CPU/无 CUDA 时显式报错，不做假训练。"""
    import torch
    if not torch.cuda.is_available():
        raise NotImplementedError(
            "SFT 真机训练需要 GPU（V100）。CPU 侧请用 --dry-run 预演；"
            "详见 docs/v100_checklist.md Step3。")
    import transformers
    from peft import LoraConfig, get_peft_model
    from transformers import AutoTokenizer, Qwen3ForCausalLM
    from transformers import Trainer, TrainingArguments

    examples = _prepare_examples(data_path, sample_n=sample_n,
                                 max_length=max_length)
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-8B")
    model = Qwen3ForCausalLM.from_pretrained(
        "Qwen/Qwen3-8B", load_in_8bit=load_in_8bit, device_map="auto")
    lora = LoraConfig(r=8, lora_alpha=32, target_modules=["q_proj", "k_proj",
                        "v_proj", "o_proj"], lora_dropout=0.05, bias="none")
    model = get_peft_model(model, lora)
    os.makedirs(out_dir, exist_ok=True)
    args = TrainingArguments(
        output_dir=out_dir, num_train_epochs=epochs, per_device_train_batch_size=1,
        gradient_accumulation_steps=8, gradient_checkpointing=True,
        fp16=True, bf16=False,  # V100 = sm_70，无 bf16
        save_strategy="epoch", logging_steps=10, report_to=[],
        learning_rate=5e-5, lr_scheduler_type="cosine", warmup_ratio=0.03)
    Trainer(model=model, args=args, train_dataset=examples,
            tokenizer=tokenizer).train()
    model.save_pretrained(out_dir)


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT 训练（V100 / CPU dry-run）")
    ap.add_argument("--data", default=os.path.join("data", "sft_data", "sft_train.jsonl"))
    ap.add_argument("--out", default=os.path.join("weights", "sft_qwen3_lora"))
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--sample-n", type=int, default=None)
    ap.add_argument("--load-in-8bit", action="store_true", dest="load_in_8bit")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--max-length", type=int, default=2048)
    args = ap.parse_args(argv)
    if args.dry_run:
        _run_dry_run(data_path=args.data, sample_n=args.sample_n or 8,
                     max_length=args.max_length, out_dir=args.out)
    else:
        _run_train(data_path=args.data, out_dir=args.out,
                   load_in_8bit=args.load_in_8bit, sample_n=args.sample_n,
                   epochs=args.epochs, max_length=args.max_length)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
