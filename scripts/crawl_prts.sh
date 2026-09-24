#!/usr/bin/env bash
# 一键批量爬取 PRTS Wiki（断点续爬，限速 1 请求/秒 + 指数退避，已内置）。
# 用法：
#   bash scripts/crawl_prts.sh                 # 默认爬三类：干员50 / 敌人50 / 关卡20
#   bash scripts/crawl_prts.sh operator 80     # 只爬干员 80 个
#   bash scripts/crawl_prts.sh enemy
#   bash scripts/crawl_prts.sh stage 20
#   ARK_FORCE=1 bash scripts/crawl_prts.sh ... # 已存在页面也强制重爬
#
# 产物：data/prts_raw/{operators,enemies,stages}/*.json（已在 .gitignore，禁止提交）。
# 注意：本脚本会联网访问 https://prts.wiki ，请遵守其 robots.txt 与使用条款，控制规模。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

TYPE="${1:-all}"
LIMIT="${2:-}"
FORCE_FLAG=""
[[ "${ARK_FORCE:-0}" == "1" ]] && FORCE_FLAG="--force"

case "$TYPE" in
  operator|enemy|stage) TYPES=("$TYPE") ;;
  all) TYPES=(operator enemy stage) ;;
  *) echo "[FAIL] 未知类型 '$TYPE'，可选：operator | enemy | stage | all"; exit 2 ;;
esac

# ---- 前置条件 ----
"$PY" -c "import requests, bs4" 2>/dev/null || {
  echo "[FAIL] 缺少爬虫依赖 requests/beautifulsoup4，请先：bash scripts/setup_env.sh"; exit 1; }
if ! "$PY" - <<'PY'
import urllib.request
urllib.request.urlopen("https://prts.wiki/robots.txt", timeout=10)
PY
then
  echo "[FAIL] 无法访问 https://prts.wiki （网络不通）；爬虫需联网，请检查网络后重试。"
  exit 1
fi

default_limit() { case "$1" in operator) echo 50;; enemy) echo 50;; stage) echo 20;; esac; }

echo "[crawl] 类型=${TYPES[*]} 输出=data/prts_raw（限速 1 req/s，断点续爬，已存在跳过）"
for t in "${TYPES[@]}"; do
  lim="${LIMIT:-$(default_limit "$t")}"
  echo "----- 爬取 $t，上限 $lim -----"
  "$PY" -m knowledge.crawler.batch_crawl --type "$t" --limit "$lim" $FORCE_FLAG
done

N=$(find data/prts_raw -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
echo "[crawl] 完成，data/prts_raw 下现有 JSON 共 $N 个（已 gitignore，不会提交）。"
echo
echo "本步骤完成。下一步："
echo "  bash scripts/build_rag.sh      # 构建向量库"
echo "  bash scripts/build_graph.sh    # 构建知识图谱"
