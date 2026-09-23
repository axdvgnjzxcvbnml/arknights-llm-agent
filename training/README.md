# training —— SFT / DPO 训练（V100）

本目录只有 **SFT 数据准备在 CPU 上真实可跑**；`sft_train.py` / `dpo_train.py` 是骨架，
真实训练全部标注 `# TODO-V100`，等单卡 V100 环境。不在 CPU 沙箱尝试任何真实训练。

## 文件

| 文件 | 状态 | 说明 |
|---|---|---|
| `sft_data_prep.py` | ✅ CPU 真实 | MAA 作业 + PRTS 语料 → question/answer JSONL |
| `sft_train.py` | ⏳ 骨架 `# TODO-V100` | LoRA 微调 Qwen3-8B（慢思考） |
| `dpo_train.py` | ⏳ 骨架 `# TODO-V100` | DPO 偏好对齐（在 SFT 权重上继续） |
| `config.py` | ✅ | 读取 `configs/training.yaml`（仅 pyyaml，轻量） |

## 一、数据格式

### 输入：MAA 作业（maa-copilot 抄作业 schema 子集）

见样例 `data/mock/maa_job_3-8.json`（**本仓库自造的联调小样例，非官方/真实作业**）。关键字段：

```json
{
  "stage_name": "3-8",
  "details": {
    "actions": [
      {"type": "部署", "kills": 0, "cost_changes": 10, "location": [3,2], "direction": "左", "name": "芬"},
      {"type": "技能", "kills": 15, "name": "芬"},
      {"type": "撤退", "kills": 40, "name": "芬"}
    ]
  }
}
```

- `type`：当前支持 `部署/技能/撤退`（映射到本项目 `deploy/skill/retreat`）；
  其余类型（快速战斗等）计数跳过，不静默编造。
- `kills` / `cost_changes`：动作触发时的击杀数 / 费用，作为"状态时间锚"。
- `location`：MAA 坐标 `[列, 行]`，**1 基、从左上角**；`direction`：上/下/左/右。

### 输出：SFT 训练对 JSONL

每行一条：

```json
{
  "question": "[关卡] ...\n[本关敌情·fact@PRTS] ...\n[进度] 已击杀K；当前费用约C。\n[已部署] ...\n[任务] ...",
  "answer": "deploy 芬 at (3,2) facing 左\n理由：\n1) ...\n2) ...\n（注：理由由作业时间轴反推 inferred，非作业作者原话）",
  "meta": {"stage":"3-8", "action":"deploy", "kills":0, "cost":10, "operator":"芬",
           "evidence": {"action":"fact:maa_job", "operator":"fact:prts",
                        "enemies":"fact:prts",
                        "rationale":"inferred:timeline_reconstructed"}}
}
```

**证据分级（重要，与全项目一致）**：

- 作业时间轴（何时对谁做什么）= `fact:maa_job`；
- PRTS 干员属性 / 关卡敌情 = `fact:prts`；
- "为什么这么做"= `inferred:timeline_reconstructed`——是我们按职业机制+时间轴**反推**的，
  不是作业作者原话，训练/使用时不得升级为专家确证理由。

**无 PRTS 语料也能跑**（fresh clone / CI 场景）：自动降级为仅用作业时间轴构造，
此时 meta 中不带 `operator/enemies` 的 fact 证据，question 显式标注"无 PRTS 语料"。

### DPO 偏好对（V100/真机阶段补）

`data/sft_data/dpo_pairs.jsonl`，每行 `{"prompt","chosen","rejected"}`，
chosen/rejected 不得相同。来源：同一状态下 Agent 较差动作 vs 人工/慢思考更优动作，
由决策日志 + 人工标注整理（当前不产出）。

## 二、CPU 上跑数据准备

```bash
# 单作业（默认读 data/mock，PRTS 用 data/prts_raw，缺失自动降级）
python -m training.sft_data_prep --job data/mock/maa_job_3-8.json
# 一个目录批量
python -m training.sft_data_prep --job /path/to/maa_jobs --prts data/prts_raw --out data/sft_data/sft_all.jsonl
```

产物（`data/sft_data/` 已 gitignore）：`sft_all.jsonl`，并按 `sft.eval_ratio`
切分出与 config 对齐的 `sft_train.jsonl` / `sft_eval.jsonl`。

## 三、超参（`configs/training.yaml`）

- LoRA：`r=16 / alpha=32 / dropout=0.05`，target_modules 覆盖 q/k/v/o/gate/up/down。
- SFT：`max_length=2048`，V100 16G 用 `per_device_batch=1 × grad_accum=16`，
  `lr=2e-4 / cosine / warmup0.03 / epochs=3`。
- DPO：`beta=0.1 / lr=5e-5 / epochs=1`。

> **V100 是 sm_70，没有 bf16 硬件支持**：配置中 SFT/DPO 都用 `fp16: true / bf16: false`，
> `torch_dtype` 在加载代码里改 float16（config 里 bfloat16 仅为注释提醒）。

## 四、V100 执行步骤（骨架补全后）

1. 先过 `docs/v100_checklist.md`（**Step 1 是编译 PointNet2 CUDA 算子**，与本训练环境隔离建 conda env）。
2. 准备数据：真机阶段采集自己的对局/作业 → `sft_data_prep` 生成 JSONL（**只提交脚本，不提交数据**）。
3. 在 `sft_train.py` 补齐：`load_tokenizer_and_model`（fp16）→ `build_lora_config`（peft）
   → `tokenize_dataset`（prompt 段 label=-100，只对 answer 计 loss）→ Trainer/训练循环。
4. `python -m training.sft_train`，权重落 `weights/sft_qwen3_lora/`（gitignore）。
5. 整理偏好对后 `python -m training.dpo_train`，落 `weights/dpo_qwen3_lora/`。
6. 把 LoRA 权重接到 `agent/slow_thinker.py` 的 `# TODO-V100` 加载处，用 mock→真机回归。

## 验证（CPU）

```bash
python -m pytest tests/test_training.py -q
```

覆盖：作业校验、动作映射、前缀已部署状态、未知动作跳过、无 PRTS 降级、落盘切分、
SFT/DPO 骨架抛 `TODO-V100`、偏好对校验、`import training` 不拉起 torch/transformers/peft。
