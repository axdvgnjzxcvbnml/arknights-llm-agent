#!/usr/bin/env bash
# 环境检查：CPU 侧开发/冒烟所需为必需项；GPU/模拟器/重模型为可选项（仅提示，不导致失败）。
# 注：第八批会随 V100 上线脚本进一步扩充 GPU 侧检查。
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

fail=0
check_required() {
  # check_required <导入名> <pip包名>
  if "$PY" -c "import $1" >/dev/null 2>&1; then
    echo "[OK]   必需依赖: $2"
  else
    echo "[FAIL] 缺少必需依赖: $2  (pip install $2)"
    fail=1
  fi
}
check_optional() {
  if "$PY" -c "import $1" >/dev/null 2>&1; then
    echo "[OK]   可选依赖: $2"
  else
    echo "[SKIP] 可选依赖未安装: $2（GPU/真机阶段需要，CPU 冒烟不影响）"
  fi
}

echo "===== Python ====="
"$PY" -V || { echo "[FAIL] 未找到 $PY"; exit 1; }

echo "===== CPU 必需依赖（冒烟/开发） ====="
check_required numpy numpy
check_required pydantic pydantic
check_required yaml pyyaml
check_required pytest pytest

echo "===== 配置文件 ====="
for f in configs/perception.yaml configs/knowledge.yaml; do
  if [[ -f "$f" ]]; then echo "[OK]   $f"; else echo "[FAIL] 缺少 $f"; fail=1; fi
done

echo "===== GPU / 真机可选组件 ====="
check_optional torch torch
check_optional ultralytics ultralytics
check_optional paddleocr paddleocr
check_optional chromadb chromadb
check_optional mcp mcp
if command -v adb >/dev/null 2>&1; then
  echo "[OK]   adb: $(command -v adb)"
else
  echo "[SKIP] 未找到 adb（真机/模拟器操作需要，CPU 冒烟不影响）"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "环境检查存在必需项缺失，请按上述提示安装。"
  exit 1
fi
echo "ENV CHECK OK（必需项齐全，可运行 bash scripts/run_smoke.sh）"
