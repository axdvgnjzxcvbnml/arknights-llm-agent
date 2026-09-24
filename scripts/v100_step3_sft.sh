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
JOB_DIR="${SFT_JOB_DIR:-data/sft_data/maa_jobs}"
PRTS_DIR="${SFT_PRTS_DIR:-data/prts_raw}"
if [[ ! -d "$JOB_DIR" ]]; then
  echo "[WARN] 作业目录 $JOB_DIR 不存在，回退 data/mock（仅样例，不能用于正式训练）。"
  JOB_DIR="data/mock"
fi
echo "[sft] 从 $JOB_DIR 读 MAA 作业 + $PRTS_DIR 读 PRTS，按关卡分组切分 -> data/sft_data（gitignore）"
"$PY" -m training.sft_data_prep --job "$JOB_DIR" --prts "$PRTS_DIR" --split-by-stage

# ---- GPU 门禁：训练必须 V100 ----
if ! "$PY" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  echo
  echo "[GATE] SFT 数据已生成；LoRA 训练需要 V100（当前无 CUDA），在此中止（退出码 3）。"
  echo "       CPU 侧可先跑管线自检：python -m training.sft_train --dry-run --max-steps 2"
  echo "       数据检查：ls data/sft_data（sft_train.jsonl / sft_eval.jsonl）；到 V100 机重跑本脚本。"
  exit 3
fi

echo
echo "===== LoRA 微调（Qwen3-8B；V100 sm_70 用 fp16，超参见 configs/training.yaml）====="
# 16G 显存默认走 QLoRA（8bit 冻结底座 + LoRA）；SFT_LOAD_8BIT=0 改纯 fp16（8B 通常会 OOM）。
EXTRA=()
if [[ "${SFT_LOAD_8BIT:-1}" == "1" ]]; then
  echo "[sft] 启用 --load-in-8bit（QLoRA，16G 推荐）；如不用可设 SFT_LOAD_8BIT=0。"
  EXTRA+=(--load-in-8bit)
fi
# 正式开训前先用 5 步实测显存/loss（设 SFT_SKIP_PROBE=1 跳过）。
if [[ "${SFT_SKIP_PROBE:-0}" != "1" ]]; then
  echo "[sft] 先跑 5 步探针（验证显存与 loss 方向）..."
  "$PY" -m training.sft_train "${EXTRA[@]}" --max-samples 80 --max-steps 5 || {
    echo "[FAIL] 5 步探针失败，先排显存/数据问题，不要直接开全量。"; exit 1; }
fi
"$PY" -m training.sft_train "${EXTRA[@]}"
RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[FAIL] sft_train 退出码 $RC；见 docs/troubleshooting.md 与 docs/v100_checklist.md。"
  exit $RC
fi
echo
echo "本步骤完成。下一步：bash scripts/v100_step4_deploy_agent.sh"
