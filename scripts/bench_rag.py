#!/usr/bin/env python3
"""RAG 检索延迟基准：向量 vs BM25 vs 混合，各跑 N 次，输出 P50/P95/平均。

用法：
    python scripts/bench_rag.py --device cpu --queries 5 --runs 20
    python scripts/bench_rag.py --device gpu  # V100 上用 GPU embedding

输出：
    results/benchmarks/bench_rag_<device>_<timestamp>.json
    终端打印人类可读汇总表
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime

# 确保仓库根在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge.rag.retriever import Retriever  # noqa: E402

DEFAULT_QUERIES = [
    "能天使的技能是什么",
    "3-8有哪些敌人",
    "碎骨的属性",
    "先锋干员的费用",
    "沉默效果是什么",
]


def percentile(data, p):
    """计算百分位数（线性插值）。"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def bench_mode(retriever, queries, runs, use_bm25):
    """跑一种检索模式，返回每条 query 的延迟列表。"""
    # 强制设置 use_bm25
    retriever.use_bm25 = use_bm25
    if use_bm25:
        _ = retriever.bm25  # 预热 BM25 索引
    results = {}
    for q in queries:
        latencies = []
        for _ in range(runs):
            t0 = time.perf_counter()
            retriever.search(q, k=5)
            latencies.append((time.perf_counter() - t0) * 1000.0)
        results[q] = latencies
    return results


def summarize(results):
    """汇总延迟统计。"""
    all_latencies = []
    for latencies in results.values():
        all_latencies.extend(latencies)
    return {
        "runs_per_query": len(list(results.values())[0]) if results else 0,
        "query_count": len(results),
        "total_samples": len(all_latencies),
        "mean_ms": round(statistics.mean(all_latencies), 3) if all_latencies else 0,
        "median_ms": round(statistics.median(all_latencies), 3) if all_latencies else 0,
        "p50_ms": round(percentile(all_latencies, 50), 3),
        "p95_ms": round(percentile(all_latencies, 95), 3),
        "p99_ms": round(percentile(all_latencies, 99), 3),
        "min_ms": round(min(all_latencies), 3) if all_latencies else 0,
        "max_ms": round(max(all_latencies), 3) if all_latencies else 0,
        "per_query": {
            q: {
                "mean_ms": round(statistics.mean(lat), 3),
                "p50_ms": round(percentile(lat, 50), 3),
                "p95_ms": round(percentile(lat, 95), 3),
            }
            for q, lat in results.items()
        },
    }


def print_table(name, summary):
    """打印人类可读汇总表。"""
    print("\n" + "=" * 60)
    print("  %s" % name)
    print("=" * 60)
    print("  样本数: %d（%d 条 query × %d 次）" % (
        summary["total_samples"], summary["query_count"], summary["runs_per_query"]))
    print("  平均:   %.2f ms" % summary["mean_ms"])
    print("  P50:    %.2f ms" % summary["p50_ms"])
    print("  P95:    %.2f ms" % summary["p95_ms"])
    print("  P99:    %.2f ms" % summary["p99_ms"])
    print("  最小:   %.2f ms" % summary["min_ms"])
    print("  最大:   %.2f ms" % summary["max_ms"])
    print("  --- 每条 query ---")
    for q, stats in summary["per_query"].items():
        print("    %-20s  mean=%.2f  p50=%.2f  p95=%.2f" % (
            q[:20], stats["mean_ms"], stats["p50_ms"], stats["p95_ms"]))


def main():
    parser = argparse.ArgumentParser(description="RAG 检索延迟基准")
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu",
                        help="运行设备（cpu=CPU embedding，gpu=CUDA embedding）")
    parser.add_argument("--runs", type=int, default=20, help="每条 query 跑多少次")
    parser.add_argument("--queries", type=int, default=5, help="使用前 N 条标准 query")
    parser.add_argument("--output-dir", default="results/benchmarks", help="输出目录")
    args = parser.parse_args()

    queries = DEFAULT_QUERIES[:args.queries]
    print("RAG 检索基准：device=%s，%d 条 query，每条 %d 次" % (
        args.device, len(queries), args.runs))

    # 初始化 Retriever（预热 embedding 模型）
    print("初始化 Retriever（预热 embedding + BM25 索引）...")
    retriever = Retriever(use_bm25=True)
    retriever.search("预热", k=1)  # 预热

    # 三种模式
    print("\n跑向量检索（纯向量，无 BM25）...")
    vec_results = bench_mode(retriever, queries, args.runs, use_bm25=False)
    vec_summary = summarize(vec_results)
    print_table("纯向量检索", vec_summary)

    print("\n跑 BM25 检索（纯关键词，无向量）...")
    # BM25 单独测：直接调 bm25_index.search
    bm25_results = {}
    for q in queries:
        latencies = []
        for _ in range(args.runs):
            t0 = time.perf_counter()
            retriever.bm25.search(q, k=5)
            latencies.append((time.perf_counter() - t0) * 1000.0)
        bm25_results[q] = latencies
    bm25_summary = summarize(bm25_results)
    print_table("纯 BM25 检索", bm25_summary)

    print("\n跑混合检索（向量 + BM25 + RRF）...")
    hybrid_results = bench_mode(retriever, queries, args.runs, use_bm25=True)
    hybrid_summary = summarize(hybrid_results)
    print_table("混合检索（向量+BM25+RRF）", hybrid_summary)

    # 输出 JSON
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(args.output_dir, "bench_rag_%s_%s.json" % (args.device, timestamp))
    report = {
        "benchmark": "rag_retrieval",
        "device": args.device,
        "timestamp": timestamp,
        "queries": queries,
        "runs_per_query": args.runs,
        "vector_only": vec_summary,
        "bm25_only": bm25_summary,
        "hybrid": hybrid_summary,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n结果已写入: %s" % output_path)

    # 对比总结
    print("\n" + "=" * 60)
    print("  对比总结")
    print("=" * 60)
    print("  %-20s  %10s  %10s  %10s" % ("模式", "P50(ms)", "P95(ms)", "平均(ms)"))
    print("  %-20s  %10.2f  %10.2f  %10.2f" % (
        "纯向量", vec_summary["p50_ms"], vec_summary["p95_ms"], vec_summary["mean_ms"]))
    print("  %-20s  %10.2f  %10.2f  %10.2f" % (
        "纯BM25", bm25_summary["p50_ms"], bm25_summary["p95_ms"], bm25_summary["mean_ms"]))
    print("  %-20s  %10.2f  %10.2f  %10.2f" % (
        "混合(RRF)", hybrid_summary["p50_ms"], hybrid_summary["p95_ms"], hybrid_summary["mean_ms"]))


if __name__ == "__main__":
    main()
