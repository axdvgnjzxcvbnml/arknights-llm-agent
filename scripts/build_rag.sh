#!/usr/bin/env bash
# 构建 RAG 向量库（ChromaDB + bge）。
set -euo pipefail
cd "$(dirname "$0")/.."

# 前置检查
python - <<'PY'
import importlib.util
for m in ("chromadb", "sentence_transformers"):
    if importlib.util.find_spec(m) is None:
        raise SystemExit("缺少依赖: %s 请先 bash scripts/setup_env.sh" % m)
PY

RAW=data/prts_raw
if [ ! -d "$RAW" ] || [ -z "$(ls -A "$RAW" 2>/dev/null)" ]; then
  echo "[前置检查] 语料目录为空: $RAW 请先 bash scripts/crawl_prts.sh" >&2
  exit 1
fi

echo "[1/2] 构建向量库 (raw_dir=$RAW)"
if [ "${ARK_REBUILD:-0}" = "1" ]; then
  python -m knowledge.rag.build_rag --rebuild
else
  python -m knowledge.rag.build_rag
fi

echo "[2/2] 校验检索"
python -m knowledge.rag.build_rag --selfcheck

echo "完成。向量库在 data/vector_store。下一步: bash scripts/build_graph.sh"
