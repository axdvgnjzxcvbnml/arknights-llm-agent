#!/usr/bin/env python3
"""MCP 6 工具延迟基准：各跑 N 次，输出 P50/P95/平均。

直接调 KnowledgeService 方法（不通过 MCP 协议，避免 server 启动开销），
测量的是工具本身的处理延迟（含 RAG 检索/图谱查询/JSON 序列化）。

用法：
    python scripts/bench_mcp.py --device cpu --runs 20
    python scripts/bench_mcp.py --device gpu  # V100 上用 GPU embedding

输出：
    results/benchmarks/bench_mcp_<device>_<timestamp>.json
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge.mcp_tools.service import KnowledgeService  # noqa: E402


def percentile(data, p):
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1 if f + 1 < len(s) else f
    return s[f] + (s[c] - s[f]) * (k - f)


# 每个工具的测试用例（用真实存在的实体）
TOOL_CASES = {
    "query_operator": {"name": "能天使"},
    "query_skill": {"operator": "能天使", "skill_name": "扫射"},
    "query_enemy": {"name": "碎骨"},
    "query_stage": {"stage_id": "3-8"},
    "search_guide": {"query": "能天使的技能是什么", "k": 5},
    "recommend_operators": {"stage_id": "3-8"},
}


def bench_tool(service, tool_name, runs):
    """跑一个工具 N 次，返回延迟列表。"""
    case = TOOL_CASES[tool_name]
    method = getattr(service, tool_name)
    latencies = []
    for _ in range(runs):
        t0 = time.perf_counter()
        method(**case)
        latencies.append((time.perf_counter() - t0) * 1000.0)
    return latencies


def summarize(latencies):
    return {
        "samples": len(latencies),
        "mean_ms": round(statistics.mean(latencies), 3),
        "median_ms": round(statistics.median(latencies), 3),
        "p50_ms": round(percentile(latencies, 50), 3),
        "p95_ms": round(percentile(latencies, 95), 3),
        "p99_ms": round(percentile(latencies, 99), 3),
        "min_ms": round(min(latencies), 3),
        "max_ms": round(max(latencies), 3),
    }


def main():
    parser = argparse.ArgumentParser(description="MCP 工具延迟基准")
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output-dir", default="results/benchmarks")
    args = parser.parse_args()

    print("MCP 工具基准：device=%s，每个工具 %d 次" % (args.device, args.runs))
    print("初始化 KnowledgeService（预热数据+图谱+RAG）...")
    service = KnowledgeService()
    warmup_timings = service.warmup()
    print("预热完成：%s" % warmup_timings)

    results = {}
    print("\n" + "=" * 70)
    print("  %-20s  %8s  %8s  %8s  %8s" % ("工具", "P50(ms)", "P95(ms)", "平均(ms)", "最大(ms)"))
    print("=" * 70)

    for tool_name in TOOL_CASES:
        print("  跑 %s..." % tool_name, end="\r")
        latencies = bench_tool(service, tool_name, args.runs)
        summary = summarize(latencies)
        results[tool_name] = summary
        print("  %-20s  %8.2f  %8.2f  %8.2f  %8.2f" % (
            tool_name, summary["p50_ms"], summary["p95_ms"],
            summary["mean_ms"], summary["max_ms"]))

    # 汇总
    all_means = [r["mean_ms"] for r in results.values()]
    print("-" * 70)
    print("  %-20s  %8s  %8s  %8.2f" % ("6工具平均", "", "", statistics.mean(all_means)))
    print("  %-20s  %8s  %8s  %8.2f" % ("最慢工具", "", "", max(all_means)))
    print("  %-20s  %8s  %8s  %8.2f" % ("最快工具", "", "", min(all_means)))

    # 输出 JSON
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(args.output_dir, "bench_mcp_%s_%s.json" % (args.device, timestamp))
    report = {
        "benchmark": "mcp_tools",
        "device": args.device,
        "timestamp": timestamp,
        "runs_per_tool": args.runs,
        "tools": results,
        "summary": {
            "mean_of_means_ms": round(statistics.mean(all_means), 3),
            "slowest_tool": max(results, key=lambda k: results[k]["mean_ms"]),
            "fastest_tool": min(results, key=lambda k: results[k]["mean_ms"]),
        },
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n结果已写入: %s" % output_path)


if __name__ == "__main__":
    main()
