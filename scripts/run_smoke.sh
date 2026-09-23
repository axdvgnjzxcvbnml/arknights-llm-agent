#!/usr/bin/env bash
# 冒烟测试：mock 全链路，不依赖 GPU / 模拟器 / PRTS 数据。
# 第三批覆盖视觉链路：截屏 -> OCR/地图 -> 状态组装(波次推算+敌情确认) -> VLM -> 状态报告。
# 后续批次会在此扩展动作/Agent 闭环。
set -euo pipefail

# 切到仓库根（scripts 的上一级），保证 configs/ 相对路径有效
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${PYTHON:-python3}"

# 仅在缺少最小依赖时补装（CI 已预装时跳过）
if ! "$PY" -c "import numpy, pydantic, yaml" >/dev/null 2>&1; then
  echo "[run_smoke] 安装最小冒烟依赖 numpy/pydantic/pyyaml ..."
  pip install -q --disable-pip-version-check numpy pydantic pyyaml
fi

echo "[run_smoke] 运行视觉 mock 全链路 ..."
"$PY" scripts/smoke_perception.py
