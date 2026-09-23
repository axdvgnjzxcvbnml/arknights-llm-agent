#!/usr/bin/env bash
# 冒烟测试：mock 全链路，不依赖 GPU / 模拟器 / PRTS 数据。
#   视觉链路(第三批)：截屏 -> OCR/地图 -> 状态(波次+敌情确认) -> VLM -> 状态报告 -> 动作占位
#   Agent链路(第五批)：感知 -> 知识 -> 慢思考 -> 桥接 -> 快反应 -> 执行 -> 反思（可解释日志）
#   环境链路(第六批)：Gym 风格 reset/step 跑完整两局（10步通关 / 3步失败）+ 对局报告
set -euo pipefail

# 切到仓库根（scripts 的上一级），保证 configs/ 相对路径有效
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${PYTHON:-python3}"

# 仅在缺少最小依赖时补装（CI 已预装时跳过）
if ! "$PY" -c "import numpy, pydantic, yaml" >/dev/null 2>&1; then
  echo "[run_smoke] 安装最小冒烟依赖 numpy/pydantic/pyyaml ..."
  pip install -q --disable-pip-version-check numpy pydantic pyyaml
fi

echo "[run_smoke] 1/3 视觉 mock 全链路 ..."
"$PY" scripts/smoke_perception.py

echo
echo "[run_smoke] 2/3 Agent mock 全链路（状态->思考->决策->执行）..."
"$PY" scripts/smoke_agent.py

echo
echo "[run_smoke] 3/3 环境封装 mock 对局（reset -> step -> is_done）..."
"$PY" scripts/smoke_env.py

echo
echo "[run_smoke] 全部冒烟通过"
