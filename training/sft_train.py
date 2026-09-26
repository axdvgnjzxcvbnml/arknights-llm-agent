# -*- coding: utf-8 -*-
# TODO-V100: 真实 8B 训练需要 V100 + CUDA。train(dry_run=False) 在无 CUDA 机器上会显式报错。
# CPU 沙箱可跑 train(dry_run=True)：用极小 Qwen3 结构（随机权重，只下载 Qwen tokenizer，
# 不下载 8B 权重）+ LoRA 跑通“数据->tokenize->forward->loss->backward->保存/回读”全链路，
# 用于在 V100 之前验证数据管线与训练代码无 bug，不产生有意义的模型。
"""SFT 微调：LoRA 微调 Qwen3-8B（慢思考模型）。

两条路径：
- 真机（V100 sm_70，fp16，无 bf16）：`python -m training.sft_train`，
  按 configs/training.yaml 加载 Qwen3-8B + peft LoRA，可加 --load-in-8bit 走 QLoRA（16G 推荐）。
- CPU 预演：`python -m training.sft_train --dry-run`，极小随机 Qwen3 + LoRA 跑 2 个 step，
  验证数据/tokenize/掩码/优化器/保存回读。

label 掩码：只对 answer（含 EOS）计算 loss，prompt 段 label=-100。
torch / transformers / peft 全部惰性导入，`import training.sft_train` 不拉起 GPU 栈。
"""

import argparse
import json
import math
import os
import tempfile

from .config import load_training_config

__all__ = [
    "load_jsonl", "build_prompt", "encode_example", "tokenize_dataset",
    "train", "main",
]

PROMPT_TEMPLATE = (
    "你是明日方舟 AI 代理。请根据当前对局状态给出下一步动作与理由，"
    "动作词表 deploy/skill/retreat/wait。\n\n{question}\n")

# CPU dry-run 用的 tokenizer（只下 tokenizer 文件，体积小；与 Qwen3-8B 同一套 Qwen 词表）
DRY_RUN_TOKENIZER = "Qwen/Qwen3-0.6B"


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


# ---------------------------------------------------------------- tokenize（纯 Python，可单测）
def encode_example(row, tokenizer, max_length):
    # type: (dict, object, int) -> dict
    """单条样本 -> input_ids/labels（python list）。prompt 段 label=-100，仅 answer+EOS 计 loss。

    超长时从 **prompt 左侧**截断（保住 answer 监督信号不被切掉）。
    """
    prompt = build_prompt(row["question"])
    answer = str(row["answer"]).strip()
    p_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    a_ids = tokenizer(answer, add_special_tokens=False)["input_ids"]
    eos = tokenizer.eos_token_id
    if eos is not None:
        a_ids = a_ids + [eos]
    total = len(p_ids) + len(a_ids)
    if total > max_length and len(p_ids) > len(a_ids):
        drop = min(total - max_length, len(p_ids))
        p_ids = p_ids[drop:]
    input_ids = p_ids + a_ids
    labels = [-100] * len(p_ids) + list(a_ids)
    if max_length and len(input_ids) > max_length:
        input_ids = input_ids[:max_length]
        labels = labels[:max_length]
    return {"input_ids": input_ids, "labels": labels,
            "attention_mask": [1] * len(input_ids)}


def tokenize_dataset(rows, tokenizer, max_length):
    # type: (list, object, int) -> list
    return [encode_example(r, tokenizer, max_length) for r in rows]


def make_collator(pad_id):
    # type: (int) -> object
    import torch

    def collate(batch):
        maxlen = max(len(b["input_ids"]) for b in batch)
        input_ids, labels, attn = [], [], []
        for b in batch:
            pad = maxlen - len(b["input_ids"])
            input_ids.append(b["input_ids"] + [pad_id] * pad)
            labels.append(b["labels"] + [-100] * pad)
            attn.append(b["attention_mask"] + [0] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
            "attention_mask": torch.tensor(attn, dtype=torch.long),
        }
    return collate


# ---------------------------------------------------------------- 模型 / LoRA（惰性导入）
def load_tokenizer(name):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(name)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


def build_model(base_model, sft_cfg, dry_run=False, tokenizer_name=None, load_in_8bit=False):
    """返回 (model, tokenizer)。

    - dry_run：极小随机 Qwen3（CPU，几十 M 参数），只下 Qwen tokenizer，不下大模型权重。
    - 真机：Qwen3-8B；V100 用 fp16；--load-in-8bit 走 QLoRA（8bit 冻结底座，16G 推荐）。
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, Qwen3Config, Qwen3ForCausalLM

    if dry_run:
        tok = AutoTokenizer.from_pretrained(tokenizer_name or DRY_RUN_TOKENIZER)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        cfg = Qwen3Config(
            vocab_size=len(tok), hidden_size=128, intermediate_size=256,
            num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
            max_position_embeddings=2048,
        )
        model = Qwen3ForCausalLM(cfg)
        model.to(torch.float32)
        return model, tok

    # TODO-V100: 以下为 V100 真机加载路径（CPU 无 CUDA 时 train() 已提前拦截，不会走到这里）
    tok = AutoTokenizer.from_pretrained(base_model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    dtype = torch.float16 if sft_cfg.get("fp16", True) else torch.float32
    if load_in_8bit:
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(
            load_in_8bit=True,
            llm_int8_threshold=6.0,
            llm_int8_has_fp16_weight=False,
        )
        model = AutoModelForCausalLM.from_pretrained(
            base_model, quantization_config=bnb, device_map={"": 0},
            trust_remote_code=bool(sft_cfg.get("trust_remote_code", True)))
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=bool(sft_cfg.get("gradient_checkpointing", True)))
    else:
        model = AutoModelForCausalLM.from_pretrained(
            base_model, torch_dtype=dtype, device_map={"": 0},
            trust_remote_code=bool(sft_cfg.get("trust_remote_code", True)))
    return model, tok


def apply_lora(model, lora_cfg):
    from peft import LoraConfig, get_peft_model
    lc = LoraConfig(
        r=int(lora_cfg.get("r", 16)),
        lora_alpha=int(lora_cfg.get("lora_alpha", 32)),
        lora_dropout=float(lora_cfg.get("lora_dropout", 0.05)),
        bias=str(lora_cfg.get("bias", "none")),
        target_modules=list(lora_cfg.get("target_modules",
                          ["q_proj", "k_proj", "v_proj", "o_proj"])),
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lc)
    return model


def _lr_mult(step, total, warmup):
    if step < warmup:
        return float(step + 1) / float(max(1, warmup))
    if total <= warmup:
        return 1.0
    p = (step - warmup) / float(total - warmup)
    return 0.5 * (1.0 + math.cos(math.pi * p))


# ---------------------------------------------------------------- 训练
def train(cfg=None, train_file=None, eval_file=None, output_dir=None,
          dry_run=False, max_steps=None, max_samples=None,
          base_model=None, tokenizer_name=None, load_in_8bit=False,
          max_length=None):
    # type: (...) -> dict
    """LoRA SFT。dry_run=True 在 CPU 跑极小模型若干 step 做管线自检。"""
    try:
        import torch
        from torch.utils.data import DataLoader
    except ImportError:
        # TODO-V100: 未安装 torch 时，真机/自检都无法运行；显式报 TODO-V100 而非裸 ModuleNotFoundError。
        raise NotImplementedError(
            "TODO-V100: 未安装 torch，SFT 训练（含 --dry-run 管线自检）需先在"
            "V100/带 torch 的环境运行；CPU 最小测试环境不安装重依赖。")

    cfg = cfg or load_training_config()
    sft_cfg = dict(cfg.get("sft", {}))
    lora_cfg = cfg.get("lora", {})
    model_cfg = cfg.get("model", {})
    data_dir = sft_cfg.get("data_dir", "data/sft_data")
    train_file = train_file or os.path.join(data_dir, sft_cfg.get("train_file", "sft_train.jsonl"))
    eval_file = eval_file or os.path.join(data_dir, sft_cfg.get("eval_file", "sft_eval.jsonl"))
    if max_length is None:
        max_length = 512 if dry_run else int(sft_cfg.get("max_length", 2048))

    if not dry_run and not torch.cuda.is_available():
        # TODO-V100: 真机 Qwen3-8B LoRA 训练必须在 V100+CUDA；CPU 不静默跑大模型。
        raise NotImplementedError(
            "TODO-V100: 未检测到 CUDA，真机 SFT 需在 V100 上运行（fp16）。"
            "CPU 侧仅可用 --dry-run 验证管线。")

    rows = load_jsonl(train_file)
    if max_samples:
        rows = rows[:max_samples]

    base_model = base_model or model_cfg.get("sft_base_model", "Qwen/Qwen3-8B")
    model, tokenizer = build_model(
        base_model, sft_cfg, dry_run=dry_run,
        tokenizer_name=tokenizer_name or DRY_RUN_TOKENIZER, load_in_8bit=load_in_8bit)
    model = apply_lora(model, lora_cfg)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    grad_ckpt = bool(sft_cfg.get("gradient_checkpointing", True)) and not dry_run
    if grad_ckpt:
        model.config.use_cache = False
        model.gradient_checkpointing_enable()
        try:
            model.enable_input_require_grads()
        except Exception:
            pass
    if not dry_run:
        model.to(device)

    enc = tokenize_dataset(rows, tokenizer, max_length)
    micro_bs = 1 if dry_run else int(sft_cfg.get("per_device_train_batch_size", 1))
    accum = 1 if dry_run else int(sft_cfg.get("gradient_accumulation_steps", 16))
    loader = DataLoader(enc, batch_size=micro_bs, shuffle=True,
                        collate_fn=make_collator(tokenizer.pad_token_id))

    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=float(sft_cfg.get("learning_rate", 2e-4)))
    micro_per_epoch = math.ceil(len(loader) / accum)
    total_steps = micro_per_epoch * (1 if dry_run else int(sft_cfg.get("num_train_epochs", 3)))
    if max_steps:
        total_steps = min(total_steps, int(max_steps))
    warmup_steps = max(1, int(round(total_steps * float(sft_cfg.get("warmup_ratio", 0.03)))))
    use_fp16 = (device.type == "cuda" and bool(sft_cfg.get("fp16", True)))
    log_every = 1 if dry_run else int(sft_cfg.get("logging_steps", 10))

    print("[sft] dry_run=%s device=%s samples=%d micro_bs=%d accum=%d opt_steps=%d max_len=%d"
          % (dry_run, device, len(enc), micro_bs, accum, total_steps, max_length))
    model.train()
    step, micro, running = 0, 0, 0.0
    losses = []
    data_iter = iter(loader)
    while step < total_steps:
        opt.zero_grad(set_to_none=True)
        for _ in range(accum):
            try:
                batch = next(data_iter)
            except StopIteration:
                data_iter = iter(loader)
                batch = next(data_iter)
            batch = {k: v.to(device) for k, v in batch.items()}
            if use_fp16:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    loss = model(**batch).loss
            else:
                loss = model(**batch).loss
            (loss / accum).backward()
            running += float(loss.detach())
            micro += 1
        for pg in opt.param_groups:
            pg["lr"] = float(sft_cfg.get("learning_rate", 2e-4)) * _lr_mult(step, total_steps, warmup_steps)
        opt.step()
        step += 1
        avg = running / micro
        losses.append(avg)
        if step % log_every == 0 or step == 1 or dry_run:
            print("[sft] opt_step %d/%d  micro=%d  loss=%.4f  lr=%.2e"
                  % (step, total_steps, micro, avg, opt.param_groups[0]["lr"]))
        running, micro = 0.0, 0

    # 保存 LoRA adapter（dry_run 存临时目录并回读验证）
    out_dir = output_dir or (sft_cfg.get("output_dir", "weights/sft_qwen3_lora"))
    if dry_run and not output_dir:
        out_dir = tempfile.mkdtemp(prefix="sft_dryrun_")
    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    saved = [f for f in os.listdir(out_dir) if f.endswith((".json", ".safetensors", ".bin", ".model"))]
    metrics = {"dry_run": dry_run, "samples": len(enc), "optimizer_steps": step,
               "loss_first": losses[0] if losses else None,
               "loss_last": losses[-1] if losses else None,
               "output_dir": out_dir, "saved_files": sorted(saved)}

    if dry_run:
        # 回读 adapter 验证 save/load 闭环
        from peft import PeftModel
        base, _ = build_model(None, sft_cfg, dry_run=True,
                              tokenizer_name=tokenizer_name or DRY_RUN_TOKENIZER)
        reloaded = PeftModel.from_pretrained(base, out_dir)
        reloaded.eval()
        with __import__("torch").no_grad():
            b0 = make_collator(tokenizer.pad_token_id)([enc[0]])
            reloaded(input_ids=b0["input_ids"], attention_mask=b0["attention_mask"])
        metrics["adapter_reload"] = "ok"
        print("[sft][dry-run] adapter 保存并回读前向成功：%s（文件 %d 个）"
              % (out_dir, len(saved)))
    else:
        print("[sft] LoRA adapter 已保存到 %s" % out_dir)
    return metrics


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT LoRA 微调（V100 真机 / CPU --dry-run）")
    ap.add_argument("--config", default=None)
    ap.add_argument("--train", default=None, help="训练 JSONL（默认 config sft.train_file）")
    ap.add_argument("--eval", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--base-model", default=None, help="真机基座（默认 config model.sft_base_model）")
    ap.add_argument("--tokenizer-name", default=None, help="dry-run 用 tokenizer（默认 Qwen3-0.6B）")
    ap.add_argument("--load-in-8bit", action="store_true", help="V100 16G：QLoRA 8bit 冻结底座")
    ap.add_argument("--max-length", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="CPU 极小模型跑通管线（不真实训练）")
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--max-samples", type=int, default=None)
    args = ap.parse_args(argv)
    cfg = load_training_config(args.config)
    train(cfg, train_file=args.train, eval_file=args.eval, output_dir=args.out,
          dry_run=args.dry_run, max_steps=args.max_steps, max_samples=args.max_samples,
          base_model=args.base_model, tokenizer_name=args.tokenizer_name,
          load_in_8bit=args.load_in_8bit, max_length=args.max_length)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
