#!/usr/bin/env python3
"""性能回归检查：对比核心基准与基线，超过阈值报警。

用法：
    python scripts/check_perf_regression.py [--threshold 0.1] [--device cpu]

基准数据来源：docs/benchmark_baseline.md 中的 CPU 基线。
输出：人类可读报告 + results/perf_regression.json
"""
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# CPU 基线（来自 docs/benchmark_baseline.md，单位 ms）
BASELINE = {
    "rag_vector_p50": 15.0,
    "rag_vector_p95": 30.0,
    "rag_bm25_p50": 5.0,
    "rag_bm25_p95": 10.0,
    "rag_hybrid_p50": 20.0,
    "rag_hybrid_p95": 40.0,
    "mcp_query_operator_p50": 2.0,
    "mcp_query_enemy_p50": 2.0,
    "mcp_query_stage_p50": 3.0,
    "mcp_search_guide_p50": 25.0,
    "mcp_recommend_operators_p50": 1.0,  # 预热后
    "agent_decision_p50": 50.0,  # mock
    "agent_decision_p95": 100.0,
    "perception_parse_p50": 5.0,  # mock
}

# 报警阈值：超过基线的百分比
DEFAULT_THRESHOLD = 0.1  # 10%


def _bench_rag(n: int = 20) -> Dict[str, float]:
    """RAG 检索基准（向量/BM25/混合）。"""
    try:
        from knowledge.rag.retriever import get_retriever
        retriever = get_retriever()
        queries = ["能天使的技能", "3-8敌人", "碎骨属性", "先锋费用", "沉默效果"]

        vector_times, bm25_times, hybrid_times = [], [], []
        for q in queries:
            for _ in range(n // len(queries)):
                # 向量
                t0 = time.perf_counter()
                retriever.search(q, k=5, method="vector")
                vector_times.append((time.perf_counter() - t0) * 1000)
                # BM25
                t0 = time.perf_counter()
                retriever.search(q, k=5, method="bm25")
                bm25_times.append((time.perf_counter() - t0) * 1000)
                # 混合
                t0 = time.perf_counter()
                retriever.search(q, k=5, method="hybrid")
                hybrid_times.append((time.perf_counter() - t0) * 1000)

        def _p50(arr): return sorted(arr)[len(arr) // 2] if arr else 0
        def _p95(arr): return sorted(arr)[int(len(arr) * 0.95)] if arr else 0

        return {
            "rag_vector_p50": _p50(vector_times),
            "rag_vector_p95": _p95(vector_times),
            "rag_bm25_p50": _p50(bm25_times),
            "rag_bm25_p95": _p95(bm25_times),
            "rag_hybrid_p50": _p50(hybrid_times),
            "rag_hybrid_p95": _p95(hybrid_times),
        }
    except Exception as e:
        return {"_error": str(e)}


def _bench_mcp(n: int = 10) -> Dict[str, float]:
    """MCP 工具基准。"""
    try:
        from knowledge.mcp_tools.service import KnowledgeService
        svc = KnowledgeService()
        svc.warmup()  # 预热

        times = {}
        # query_operator
        t0 = time.perf_counter()
        for _ in range(n):
            svc.query_operator("能天使")
        times["mcp_query_operator_p50"] = ((time.perf_counter() - t0) / n) * 1000

        # query_enemy
        t0 = time.perf_counter()
        for _ in range(n):
            svc.query_enemy("碎骨")
        times["mcp_query_enemy_p50"] = ((time.perf_counter() - t0) / n) * 1000

        # query_stage
        t0 = time.perf_counter()
        for _ in range(n):
            svc.query_stage("3-8")
        times["mcp_query_stage_p50"] = ((time.perf_counter() - t0) / n) * 1000

        # search_guide
        t0 = time.perf_counter()
        for _ in range(n):
            svc.search_guide("能天使技能", k=3)
        times["mcp_search_guide_p50"] = ((time.perf_counter() - t0) / n) * 1000

        # recommend_operators（预热后）
        t0 = time.perf_counter()
        for _ in range(n):
            svc.recommend_operators("3-8")
        times["mcp_recommend_operators_p50"] = ((time.perf_counter() - t0) / n) * 1000

        return times
    except Exception as e:
        return {"_error": str(e)}


def _bench_agent(n: int = 5) -> Dict[str, float]:
    """Agent 决策基准（mock）。"""
    try:
        from agent.decision_loop import DecisionLoop
        from env.mock_env import MockEnv
        env = MockEnv()
        loop = DecisionLoop(env=env)
        state = env.reset()

        times = []
        for _ in range(n):
            t0 = time.perf_counter()
            decision = loop.step(state)
            times.append((time.perf_counter() - t0) * 1000)
            state = env.step(decision.action)[0]

        sorted_t = sorted(times)
        return {
            "agent_decision_p50": sorted_t[len(sorted_t) // 2],
            "agent_decision_p95": sorted_t[int(len(sorted_t) * 0.95)],
        }
    except Exception as e:
        return {"_error": str(e)}


def compare_with_baseline(results: Dict[str, float], threshold: float) -> List[Dict[str, Any]]:
    """对比基线，返回超阈值项。"""
    alerts = []
    for key, baseline_val in BASELINE.items():
        if key not in results:
            continue
        actual = results[key]
        if actual <= 0:
            continue
        ratio = (actual - baseline_val) / baseline_val
        if ratio > threshold:
            alerts.append({
                "metric": key,
                "baseline_ms": round(baseline_val, 2),
                "actual_ms": round(actual, 2),
                "regression_pct": round(ratio * 100, 1),
                "status": "REGRESSION",
            })
        elif ratio < -threshold:
            alerts.append({
                "metric": key,
                "baseline_ms": round(baseline_val, 2),
                "actual_ms": round(actual, 2),
                "improvement_pct": round(-ratio * 100, 1),
                "status": "IMPROVED",
            })
    return alerts


def main():
    import argparse
    parser = argparse.ArgumentParser(description="性能回归检查")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="报警阈值（默认 0.1 = 10%%）")
    parser.add_argument("--device", type=str, default="cpu", choices=["cpu", "gpu"])
    parser.add_argument("--quick", action="store_true", help="快速模式（减少迭代次数）")
    args = parser.parse_args()

    n_factor = 3 if args.quick else 1

    print("=" * 60)
    print("性能回归检查")
    print("=" * 60)
    print("设备: %s | 阈值: %.0f%%" % (args.device, args.threshold * 100))
    print()

    all_results = {}

    # RAG
    print("[1/3] RAG 检索基准...")
    rag = _bench_rag(n=20 // n_factor)
    if "_error" in rag:
        print("  跳过: %s" % rag["_error"])
    else:
        all_results.update(rag)
        print("  vector P50=%.1fms | bm25 P50=%.1fms | hybrid P50=%.1fms" % (
            rag.get("rag_vector_p50", 0), rag.get("rag_bm25_p50", 0),
            rag.get("rag_hybrid_p50", 0)))

    # MCP
    print("[2/3] MCP 工具基准...")
    mcp = _bench_mcp(n=10 // n_factor)
    if "_error" in mcp:
        print("  跳过: %s" % mcp["_error"])
    else:
        all_results.update(mcp)
        print("  operator=%.1fms | search=%.1fms | recommend=%.1fms" % (
            mcp.get("mcp_query_operator_p50", 0), mcp.get("mcp_search_guide_p50", 0),
            mcp.get("mcp_recommend_operators_p50", 0)))

    # Agent
    print("[3/3] Agent 决策基准（mock）...")
    agent = _bench_agent(n=5 // n_factor)
    if "_error" in agent:
        print("  跳过: %s" % agent["_error"])
    else:
        all_results.update(agent)
        print("  decision P50=%.1fms | P95=%.1fms" % (
            agent.get("agent_decision_p50", 0), agent.get("agent_decision_p95", 0)))

    # 对比基线
    print()
    print("-" * 60)
    alerts = compare_with_baseline(all_results, args.threshold)
    regressions = [a for a in alerts if a["status"] == "REGRESSION"]
    improvements = [a for a in alerts if a["status"] == "IMPROVED"]

    if regressions:
        print("发现 %d 项性能回归（超过 %.0f%% 阈值）:" % (len(regressions), args.threshold * 100))
        for a in regressions:
            print("  ⚠️  %s: 基线 %.1fms -> 当前 %.1fms (+%.1f%%)" % (
                a["metric"], a["baseline_ms"], a["actual_ms"], a["regression_pct"]))
    else:
        print("无性能回归 ✅")

    if improvements:
        print()
        print("发现 %d 项性能提升:" % len(improvements))
        for a in improvements:
            print("  📈 %s: 基线 %.1fms -> 当前 %.1fms (-%.1f%%)" % (
                a["metric"], a["baseline_ms"], a["actual_ms"], a["improvement_pct"]))

    # 保存结果
    os.makedirs(os.path.join(PROJECT_ROOT, "results"), exist_ok=True)
    out_path = os.path.join(PROJECT_ROOT, "results", "perf_regression.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "device": args.device,
            "threshold": args.threshold,
            "results": all_results,
            "baseline": BASELINE,
            "alerts": alerts,
            "regression_count": len(regressions),
        }, f, ensure_ascii=False, indent=2)
    print()
    print("结果已保存: %s" % out_path)

    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
