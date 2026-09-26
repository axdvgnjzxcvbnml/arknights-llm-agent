# 性能回归指南

> 最后更新：2026-09-27

## 一、工具说明

`scripts/check_perf_regression.py` 是性能回归检查脚本，对比核心基准与 CPU 基线，超过 10% 阈值报警。

```bash
# 完整检查
python scripts/check_perf_regression.py

# 快速模式（迭代次数减少，用于 CI）
python scripts/check_perf_regression.py --quick

# 自定义阈值
python scripts/check_perf_regression.py --threshold 0.2
```

## 二、覆盖的基准指标

| 类别 | 指标 | 基线（CPU, ms） |
| --- | --- | --- |
| RAG | rag_vector_p50/p95 | 15 / 30 |
| RAG | rag_bm25_p50/p95 | 5 / 10 |
| RAG | rag_hybrid_p50/p95 | 20 / 40 |
| MCP | mcp_query_operator_p50 | 2 |
| MCP | mcp_query_enemy_p50 | 2 |
| MCP | mcp_query_stage_p50 | 3 |
| MCP | mcp_search_guide_p50 | 25 |
| MCP | mcp_recommend_operators_p50 | 1（预热后） |
| Agent | agent_decision_p50/p95 | 50 / 100（mock） |
| Perception | perception_parse_p50 | 5（mock） |

## 三、CI 集成

在 `.github/workflows/ci.yml` 中加一个可选的 `perf-regression` job（不阻塞）：

```yaml
perf-regression:
  runs-on: ubuntu-latest
  needs: [smoke-test]
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.12" }
    - run: pip install -r requirements.txt
    - run: python scripts/check_perf_regression.py --quick
      continue-on-error: true  # 不阻塞，只记录
```

## 四、V100 对比

V100 上线后，用 `--device gpu` 参数跑 GPU 基准，与 CPU 基线对比：

```bash
# V100 上跑 GPU 基准
python scripts/check_perf_regression.py --device gpu

# 预期提升：
# - RAG embedding: CPU 15ms -> GPU 3ms (5x)
# - Agent 决策: mock 50ms -> 真实 1500ms (Qwen3-8B)
# - MCP recommend: 1ms -> 1ms (无 GPU 依赖)
```

注意：Agent 决策的 GPU 基准会比 mock 慢很多（模型推理 1-2 秒），这是预期行为，不算回归。

## 五、已知性能瓶颈

| 瓶颈 | 原因 | 修复状态 |
| --- | --- | --- |
| recommend_operators 首次 7.2s | KnowledgeService 懒加载 | ✅ 已修复（预热+pickle） |
| RAG 首次检索 5s | ChromaDB + embedding 模型冷启动 | ⚠️ 启动时预热 |
| 图谱加载 6s | GraphML 83MB 解析 | ✅ 已修复（pickle 54MB/1s） |
| BM25 索引构建 30s | 13511 chunk 分词+建索引 | ⚠️ 缓存到磁盘，首次构建后增量 |

## 六、输出格式

脚本输出：
1. 人类可读报告（终端）
2. `results/perf_regression.json`（机器可读，含基线/当前值/报警项）

退出码：0=无回归，1=有回归。
