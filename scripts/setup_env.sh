#!/usr/bin/env bash
# 一键安装依赖 + 关键库版本检查。
# 用法：
#   bash scripts/setup_env.sh              # 完整安装 requirements.txt（面向 V100/完整功能）
#   bash scripts/setup_env.sh --minimal    # 只装 CPU 冒烟/开发最小依赖（numpy/pydantic/pyyaml/pytest/rich）
#   ARK_SKIP_PIP=1 bash scripts/setup_env.sh   # 跳过 pip，只做版本检查（CI/已装环境用）
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"
MINIMAL=0
for a in "$@"; do [[ "$a" == "--minimal" ]] && MINIMAL=1; done

echo "===== Python 解释器 ====="
"$PY" -V || { echo "[FAIL] 未找到 $PY"; exit 1; }

if [[ "${ARK_SKIP_PIP:-0}" == "1" ]]; then
  echo "[setup] ARK_SKIP_PIP=1，跳过安装，仅检查版本。"
elif [[ "$MINIMAL" == "1" ]]; then
  echo "===== 安装最小依赖（CPU 冒烟/开发） ====="
  "$PY" -m pip install -q --disable-pip-version-check numpy pydantic pyyaml pytest rich
else
  echo "===== 安装完整依赖 requirements.txt（含 GPU/视觉/知识库栈） ====="
  echo "[setup] 提示：完整安装含 torch/ultralytics/paddleocr，体积较大。"
  echo "[setup]       仅跑 mock 冒烟可用：bash scripts/setup_env.sh --minimal"
  "$PY" -m pip install --disable-pip-version-check -r requirements.txt
fi

echo
echo "===== 关键库版本检查 ====="
"$PY" - <<'PYEOF'
import importlib
mods = [
    ("numpy", "numpy"), ("pydantic", "pydantic"), ("yaml", "pyyaml"),
    ("pytest", "pytest"), ("rich", "rich"),
    ("torch", "torch"), ("transformers", "transformers"),
    ("chromadb", "chromadb"),
    ("sentence_transformers", "sentence-transformers"),
    ("networkx", "networkx"), ("cv2", "opencv-python"),
    ("ultralytics", "ultralytics"), ("mcp", "mcp"),
]
missing = []
for imp, pip_name in mods:
    try:
        m = importlib.import_module(imp)
        ver = getattr(m, "__version__", "?")
        extra = ""
        if imp == "torch":
            try:
                import torch
                extra = " | cuda_available=%s" % torch.cuda.is_available()
                if torch.cuda.is_available():
                    extra += " | %s" % torch.cuda.get_device_name(0)
            except Exception as e:  # noqa
                extra = " | cuda检查失败:%s" % e
        print("[OK]   %-22s %s%s" % (pip_name, ver, extra))
    except Exception:
        print("[MISS] %-22s 未安装（完整功能需要；最小冒烟可忽略）" % pip_name)
        missing.append(pip_name)
core = {"numpy", "pydantic", "pyyaml", "pytest"}
hard = [m for m in missing if m in core]
if hard:
    print("[FAIL] 核心依赖缺失：%s；请重试或用 --minimal" % ", ".join(hard))
    raise SystemExit(1)
print("[setup] 核心依赖齐全。")
PYEOF

echo
echo "本步骤完成。下一步："
echo "  - 仅验证环境      → bash scripts/check_env.sh && bash scripts/run_smoke.sh"
echo "  - 构建知识库(可选) → bash scripts/crawl_prts.sh all   # 需联网，产物 gitignore"
echo "  - V100 机器       → bash scripts/v100_step1_setup.sh"
