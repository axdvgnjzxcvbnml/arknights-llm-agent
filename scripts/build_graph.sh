#!/usr/bin/env bash
# 一键构建知识图谱（NetworkX）：干员-技能-敌人-关卡，fact/inferred 分级。
# 用法：bash scripts/build_graph.sh
# 输入：data/prts_raw/**/*.json
# 输出：data/graph/arknights_graph.graphml + build_stats.json（已 gitignore）。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

# ---- 前置条件 ----
"$PY" -c "import networkx" 2>/dev/null || {
  echo "[FAIL] 缺少 networkx，请先：bash scripts/setup_env.sh"; exit 1; }
N=$(find data/prts_raw -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
if [[ "$N" -lt 1 ]]; then
  echo "[FAIL] data/prts_raw 下没有 JSON（当前 $N 个）。请先运行：bash scripts/crawl_prts.sh"
  exit 1
fi
echo "[build_graph] 输入 JSON $N 个；输出=data/graph/arknights_graph.graphml"
"$PY" -m knowledge.graph.build_graph

if [[ -f data/graph/arknights_graph.graphml ]]; then
  echo "[build_graph] GraphML 已生成。"
else
  echo "[FAIL] 未找到输出 data/graph/arknights_graph.graphml"; exit 1
fi
echo
echo "本步骤完成。下一步："
echo "  查询验证：python -m knowledge.graph.query_graph"
echo "  启动 MCP  ：python -m knowledge.mcp_tools.server   # stdio，供 Agent 调用"
echo "  V100 部署 ：bash scripts/v100_step1_setup.sh"
