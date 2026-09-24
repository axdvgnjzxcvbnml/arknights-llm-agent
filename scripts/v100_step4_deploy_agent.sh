#!/usr/bin/env bash
# V100 部署 Agent（第四步）。先检查知识库产物与 mock 回归，再 GPU 门禁。
set -euo pipefail
cd "$(dirname "$0")/.."

# 知识库产物检查
for f in data/vector_store data/graph/arknights_graph.graphml; do
  if [ ! -e "$f" ]; then
    echo "[前置检查] 缺少 $f 请先 bash scripts/build_rag.sh && bash scripts/build_graph.sh" >&2
    exit 1
  fi
done

# mock 回归（任意机器）
echo "[1/3] mock 回归"
bash scripts/run_smoke.sh

# GPU 门禁
echo "[2/3] GPU 门禁"
python - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit(3)
PY
status=$?
if [ $status -eq 3 ]; then
  echo "[GPU 门禁] 未检测到 CUDA，安全中止（不做假部署）。" >&2
  exit 3
fi

echo "[3/3] 部署清单 # TODO-V100"
echo "1. adb: MuMu 7555 连通 (action/adb_controller.py)"
echo "2. 模型: 慢思考/快反应/VLM/bridge 加载完成 (agent/*)"
echo "3. 组件注入: env/arknights_env.py 换真实 perception/executor"
echo "4. 先打简单关: 1-7 / 2-8 / 3-8"
echo "参考: docs/v100_checklist.md Step4"

echo "== Step4 完成（清单执行） =="
echo "下一步: bash scripts/v100_step5_eval.sh"
