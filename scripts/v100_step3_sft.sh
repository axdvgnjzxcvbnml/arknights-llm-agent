#!/usr/bin/env bash
# V100 SFT 训练（第三步）。先 CPU 数据准备，再 GPU 训练。
set -euo pipefail
cd "$(dirname "$0")/.."

# 1) CPU 数据准备（任意机器可跑；全量约 18080 条，见 docs/sft_data_quality.md）
echo "[1/3] CPU: SFT 数据准备"
if [ -d data/sft_data ] && [ -f data/sft_data/sft_train.jsonl ]; then
  echo "已存在 sft_train.jsonl，跳过（ARK_SFT_REBUILD=1 强制重建）"
else
  python -m training.sft_data_prep --job data/sft_data/maa_jobs --prts data/prts_raw --split-by-stage
fi

# 2) 质量审计（CPU）
echo "[2/3] CPU: 质量审计"
python -m training.sft_quality_audit --file data/sft_data/sft_train.jsonl --n 50 || {
  echo "[审计失败] 请先检查数据（docs/sft_data_quality.md）" >&2; exit 1; }

# 3) GPU 训练（门禁）
python - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit(3)
PY
status=$?
if [ $status -eq 3 ]; then
  echo "[GPU 门禁] 未检测到 CUDA，安全中止（不做假训练）。" >&2
  exit 3
fi

echo "[3/3] GPU: SFT 训练（# TODO-V100）"
python -m training.sft_train --load-in-8bit   # 显存不足时 QLoRA 8bit；见 v100_checklist

echo "== Step3 完成 =="
echo "产物: weights/sft_qwen3_lora/（gitignore）。下一步: bash scripts/v100_step4_deploy_agent.sh"
