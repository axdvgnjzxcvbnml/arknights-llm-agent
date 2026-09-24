#!/usr/bin/env bash
# V100 Step3：SFT 数据准备（CPU 即可）+ LoRA 微调慢思考模型（需 V100）。
# 无 GPU 时由门禁拦截训练（退出码 3）；数据准备可单独在 CPU 运行。
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

echo "===== V100 Step3：SFT ====="

# ---- 前置：数据准备是 CPU 真实实现，先确保作业/语料就绪 ----
if [[ ! -d data/prts_raw ]] || [[ -z "$(find data/prts_raw -name '*.json' -print -quit 2>/dev/null)" ]]; then
  echo "[WARN] 无 PRTS 语料 data/prts_raw；将仅用作业时间轴生成（自动降级，理由不含 PRTS 事实）。"
fi
JOB_DIR="${SFT_JOB_DIR:-data/mock}"
echo "[sft] 从 $JOB_DIR 读取 MAA 作业，生成 SFT JSONL -> data/sft_data（gitignore）"
"$PY" -m training.sft_data_prep --job "$JOB_DIR"

# ---- GPU 门禁：训练必须 V100 ----
if ! "$PY" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  echo
  echo "[GATE] SFT 数据已生成；LoRA 训练需要 V100（当前无 CUDA），在此中止（退出码 3）。"
  echo "       数据检查：ls data/sft_data；到 V100 机重跑本脚本即可继续训练。"
  exit 3
fi

echo
echo "===== LoRA 微调（Qwen3-8B，fp16；超参见 configs/training.yaml）====="
# TODO-V100: training/sft_train.py 的 tokenizer/LoRA/Trainer 当前为 NotImplementedError，
#   在 V100 补齐实现后，下一行才会真正训练并输出 weights/sft_qwen3_lora（gitignore）。
"$PY" -m training.sft_train
RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[TODO-V100] sft_train 尚未实现（当前按设计抛出 TODO-V100）；请补齐 training/sft_train.py。"
  exit $RC
fi
echo
echo "本步骤完成。下一步：bash scripts/v100_step4_deploy_agent.sh"
