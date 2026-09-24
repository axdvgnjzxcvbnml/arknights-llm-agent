#!/usr/bin/env bash
# 爬取 PRTS 语料：bash scripts/crawl_prts.sh [operator|enemy|stage|all] [limit]
set -euo pipefail
cd "$(dirname "$0")/.."

KIND="${1:-all}"
LIMIT="${2:-}"

python - <<'PY'
import importlib.util
for m in ("requests", "bs4"):
    if importlib.util.find_spec(m) is None:
        raise SystemExit("缺少依赖: %s 请先 bash scripts/setup_env.sh" % m)
PY

case "$KIND" in
  operator|enemy|stage|all) ;;
  *) echo "用法: $0 [operator|enemy|stage|all] [limit]" >&2; exit 2 ;;
esac

EXTRA=()
if [ -n "$LIMIT" ]; then EXTRA+=(--limit "$LIMIT"); fi

echo "[爬取] kind=$KIND limit=${LIMIT:-默认}"
python -m knowledge.crawler.crawl_prts "$KIND" "${EXTRA[@]}"

echo "完成。语料在 data/prts_raw。下一步: bash scripts/build_rag.sh && bash scripts/build_graph.sh"
