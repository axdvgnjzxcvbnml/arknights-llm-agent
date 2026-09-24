#!/usr/bin/env bash
# 构建知识图谱（NetworkX → GraphML）。
set -euo pipefail
cd "$(dirname "$0")/.."

python - <<'PY'
import importlib.util
for m in ("networkx", "yaml"):
    if importlib.util.find_spec(m) is None:
        raise SystemExit("缺少依赖: %s 请先 bash scripts/setup_env.sh" % m)
PY

if [ ! -d data/prts_raw ] || [ -z "$(ls -A data/prts_raw 2>/dev/null)" ]; then
  echo "[前置检查] 语料目录为空: data/prts_raw 请先 bash scripts/crawl_prts.sh" >&2
  exit 1
fi

echo "[1/1] 构建图谱"
python -m knowledge.graph.build_graph --root data/prts_raw --out data/graph/arknights_graph.graphml --config configs/knowledge.yaml

if [ ! -f data/graph/arknights_graph.graphml ]; then
  echo "[错误] 图谱未落盘" >&2
  exit 1
fi

echo "完成。图谱在 data/graph/arknights_graph.graphml。下一步: 启动 api 服务读取图谱 (docs/api.md)"
