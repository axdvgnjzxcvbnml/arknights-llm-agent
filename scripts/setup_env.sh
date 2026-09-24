#!/usr/bin/env bash
# 安装/校验 Python 依赖。
#   用法: bash scripts/setup_env.sh [--minimal]
#   --minimal   只检查关键库版本，不执行 pip install
#   ARK_SKIP_PIP=1 即使非 minimal 也跳过 pip install（仅打印待装项）
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-full}"

if [ "$MODE" = "--minimal" ]; then
  python - <<'PY'
import importlib.util
mods = ["fastapi", "uvicorn", "chromadb", "sentence_transformers", "networkx",
        "yaml", "requests", "bs4", "httpx"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
if missing:
    print("缺失: %s" % ", ".join(missing))
    raise SystemExit(1)
print("依赖齐全。")
PY
  exit 0
fi

if [ "${ARK_SKIP_PIP:-0}" = "1" ]; then
  echo "[跳过 pip] 将安装: pip install -r requirements.txt"
else
  pip install -r requirements.txt
fi

python - <<'PY'
import sys
try:
    import torch
    print("torch %s (cuda=%s)" % (torch.__version__, torch.cuda.is_available()))
except Exception as e:
    print("torch 未安装（CPU 侧可选）: %s" % e)
PY

echo "完成。下一步: bash scripts/crawl_prts.sh（爬取语料）"
