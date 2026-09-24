#!/usr/bin/env bash
# 一键构建 RAG 向量库（ChromaDB，collection=arknights_knowledge，upsert 去重）。
# 用法：
#   bash scripts/build_rag.sh             # 增量 upsert（断点/更新友好）
#   ARK_REBUILD=1 bash scripts/build_rag.sh   # 清空 collection 后全量重建
#
# 输入：data/prts_raw/**/*.json；输出：data/vector_store/（已 gitignore）。
# embedding：BAAI/bge-small-zh-v1.5（首次需联网下载约90MB；离线自动回退 mock 向量，仅联调用）。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

# ---- 前置条件 ----
"$PY" -c "import chromadb, sentence_transformers" 2>/dev/null || {
  echo "[FAIL] 缺少 chromadb/sentence-transformers，请先：bash scripts/setup_env.sh"; exit 1; }
N=$(find data/prts_raw -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
if [[ "$N" -lt 1 ]]; then
  echo "[FAIL] data/prts_raw 下没有 JSON（当前 $N 个）。请先运行：bash scripts/crawl_prts.sh"
  exit 1
fi
echo "[build_rag] 输入 JSON $N 个；persist=data/vector_store；collection=arknights_knowledge"

REBUILD_FLAG=""
[[ "${ARK_REBUILD:-0}" == "1" ]] && REBUILD_FLAG="--rebuild"
"$PY" -m knowledge.rag.build_rag $REBUILD_FLAG

echo
echo "本步骤完成。下一步："
echo "  bash scripts/build_graph.sh                       # 构建知识图谱"
echo "  检索验证：python -m knowledge.rag.retrieval_test   # 5 条标准 query 相关性检查"
