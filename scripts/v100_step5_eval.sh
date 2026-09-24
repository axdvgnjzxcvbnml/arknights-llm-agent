#!/usr/bin/env bash
# 评估（第五步）。任意机器先跑 mock 基线；真机批量评估 # TODO-V100。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/2] mock 评估基线（reward 口径: 通关+100/漏怪-10/溢出-1，env/reward.py）"
python -m env.mock_env

if [ "${ARK_REAL_EVAL:-0}" = "1" ]; then
  echo "[2/2] 真机批量评估 # TODO-V100"
  python - <<'PY'
import os
os.environ.setdefault("ARK_REAL", "1")
from env.arknights_env import ArknightsEnv, build_mock_env
print("真机评估待接入（docs/v100_checklist.md Step5）")
PY
else
  echo "[2/2] 跳过真机评估（设置 ARK_REAL_EVAL=1 开启）"
fi

echo "== Step5 完成 =="
echo "结果记录: docs/experiment_log.md 追加一节（模板见文件头）"
