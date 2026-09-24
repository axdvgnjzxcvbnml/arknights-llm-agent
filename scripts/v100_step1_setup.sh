#!/usr/bin/env bash
# V100 Step1：环境检查（只检查、不改动环境）。
# 明日方舟 Agent 不使用 PointNet2（那是毕设 pointcloud-registration-detection 的 CUDA 算子），
# 因此本步骤【不编译 PointNet2】，只核对本机 GPU/torch-CUDA/关键依赖/adb 是否就绪。
# 本脚本在无 GPU 的机器上也能运行（CUDA 缺失给警告，不致命），退出码 0。
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

echo "===== V100 Step1 环境检查 ====="
"$PY" -V

echo
echo "===== GPU / CUDA ====="
"$PY" - <<'PY'
import sys
try:
    import torch
except Exception:
    print("[FAIL] 未安装 torch；请在 V100 机执行 bash scripts/setup_env.sh")
    sys.exit(0)
print("torch:", torch.__version__)
print("torch.version.cuda:", torch.version.cuda)
print("cuda.is_available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
    major, minor = torch.cuda.get_device_capability(0)
    print("capability: sm_%d%d（V100 应为 sm_70；训练用 fp16，不用 bf16）" % (major, minor))
else:
    print("[WARN] 未检测到可用 CUDA：当前不是 V100 运行环境，后续 step2/3/4 将被 GPU 门禁拦截。")
PY

echo
echo "===== V100 关键依赖 ====="
"$PY" - <<'PY'
import importlib
for imp, pip_name in [
    ("transformers", "transformers"), ("peft", "peft"), ("trl", "trl"),
    ("chromadb", "chromadb"), ("sentence_transformers", "sentence-transformers"),
    ("ultralytics", "ultralytics"), ("cv2", "opencv-python"),
]:
    try:
        m = importlib.import_module(imp)
        print("[OK]   %-22s %s" % (pip_name, getattr(m, "__version__", "?")))
    except Exception:
        print("[MISS] %-22s（视觉/训练阶段需要）" % pip_name)
# paddleocr 单独提示（import 名即 paddleocr）
try:
    import paddleocr  # noqa
    print("[OK]   %-22s %s" % ("paddleocr", getattr(paddleocr, "__version__", "?")))
except Exception:
    print("[MISS] paddleocr              （费用 OCR 需要，CPU/GPU 均可）")
PY

echo
echo "===== 模拟器 / ADB（真机阶段）====="
if command -v adb >/dev/null 2>&1; then
  echo "[OK] adb: $(command -v adb)"
  adb devices 2>/dev/null | sed 's/^/    /'
else
  echo "[MISS] 未找到 adb（真机连接 MuMu 时需要：adb connect 127.0.0.1:7555）"
fi

echo
echo "===== 关于 PointNet2（重要，避免串项目）====="
echo "PointNet2 是毕设 pointcloud-registration-detection 的 CUDA 算子，本项目不依赖、不编译。"
echo "如要处理毕设，请切到该项目独立 conda env；排障见 docs/troubleshooting.md 的 PointNet2 章节。"

echo
echo "本步骤完成。下一步："
echo "  bash scripts/v100_step2_train_vision.sh   # YOLO 视觉训练（需 CUDA）"
echo "  （或先构建知识库：crawl_prts.sh → build_rag.sh → build_graph.sh）"
