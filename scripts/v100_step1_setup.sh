#!/usr/bin/env bash
# V100 环境检查（第一步）。无 GPU 仅告警不中止。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Step1: V100 环境检查 =="
python - <<'PY'
import sys
has_gpu = False
try:
    import torch
    print("torch %s" % torch.__version__)
    if torch.cuda.is_available():
        cap = torch.cuda.get_device_capability(0)
        print("CUDA 可用: %s (sm_%d%d)" % (torch.cuda.get_device_name(0), cap[0], cap[1]))
        if cap[0] != 7:
            print("警告: 目标算力 sm_70，当前 %d%d" % (cap[0], cap[1]))
        has_gpu = True
    else:
        print("CUDA 不可用（CPU 侧可继续骨架开发）")
except Exception as e:
    print("torch 未安装或不可用: %s" % e)
PY

python - <<'PY'
import importlib.util
mods = ["peft", "trl", "transformers", "fastapi", "chromadb", "sentence_transformers",
        "networkx", "ultralytics", "paddleocr", "cv2", "requests", "bs4"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
if missing:
    print("缺失依赖: %s" % ", ".join(missing))
    raise SystemExit(1)
print("依赖齐全。")
PY

if command -v adb >/dev/null 2>&1; then
  echo "adb: $(adb version | head -1)"
else
  echo "警告: adb 未安装（部署阶段需要）"
fi

echo "== Step1 完成 =="
echo "下一步: bash scripts/v100_step2_train_vision.sh（视觉训练）"
echo "说明: 不编译 PointNet2（毕设 pointcloud 仓的 CUDA 算子，与本项目无关）"
