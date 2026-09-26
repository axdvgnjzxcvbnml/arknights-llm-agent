#!/usr/bin/env python3
"""Agent 决策延迟基准：跑 N 局完整 mock 对局，输出每步六段延迟分布。

测量：perceive / knowledge / slow / bridge / fast / execute 六段延迟，
以及端到端单步总延迟。用 mock 组件（不依赖 GPU/模拟器）。

用法：
    python scripts/bench_agent.py --device cpu --episodes 10 --steps 8
    python scripts/bench_agent.py --device gpu  # V100 上用真实模型

输出：
    results/benchmarks/bench_agent_<device>_<timestamp>.json
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from env.mock_env import build_mock_env  # noqa: E402


def percentile(data, p):
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1 if f + 1 < len(s) else f
    return s[f] + (s[c] - s[f]) * (k - f)


LATENCY_KEYS = ["perceive_ms", "knowledge_ms", "slow_ms", "bridge_ms", "fast_ms", "execute_ms"]


def run_episode(steps, stage_id="3-8"):
    """跑一局，返回每步的延迟 dict 列表。"""
    env = build_mock_env(mode="win", stage_id=stage_id, win_in=steps)
    log = env.run_episode(max_steps=steps)
    latencies = []
    for step in log.steps:
        lat = dict(step.latency_ms)
        lat["total_ms"] = sum(lat.get(k, 0.0) for k in LATENCY_KEYS)
        latencies.append(lat)
    return latencies


def summarize_list(values):
    return {
        "samples": len(values),
        "mean_ms": round(statistics.mean(values), 3),
        "p50_ms": round(percentile(values, 50), 3),
        "p95_ms": round(percentile(values, 95), 3),
        "p99_ms": round(percentile(values, 99), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
    }


def main():
    parser = argparse.ArgumentParser(description="Agent 决策延迟基准")
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--episodes", type=int, default=10, help="跑多少局")
    parser.add_argument("--steps", type=int, default=8, help="每局多少步")
    parser.add_argument("--output-dir", default="results/benchmarks")
    args = parser.parse_args()

    print("Agent 决策基准：device=%s，%d 局 × %d 步 = %d 步" % (
        args.device, args.episodes, args.steps, args.episodes * args.steps))

    all_latencies = []
    episode_times = []

    for ep in range(args.episodes):
        t0 = time.perf_counter()
        latencies = run_episode(args.steps)
        ep_time = (time.perf_counter() - t0) * 1000.0
        episode_times.append(ep_time)
        all_latencies.extend(latencies)
        print("  局 %d/%d：%d 步，耗时 %.0f ms" % (ep + 1, args.episodes, len(latencies), ep_time))

    # 按段统计
    print("\n" + "=" * 70)
    print("  %-15s  %8s  %8s  %8s  %8s  %8s" % (
        "阶段", "P50(ms)", "P95(ms)", "平均(ms)", "最小(ms)", "最大(ms)"))
    print("=" * 70)

    per_stage = {}
    for key in LATENCY_KEYS + ["total_ms"]:
        values = [lat.get(key, 0.0) for lat in all_latencies]
        summary = summarize_list(values)
        per_stage[key] = summary
        label = key.replace("_ms", "")
        print("  %-15s  %8.2f  %8.2f  %8.2f  %8.2f  %8.2f" % (
            label, summary["p50_ms"], summary["p95_ms"],
            summary["mean_ms"], summary["min_ms"], summary["max_ms"]))

    # 局级统计
    ep_summary = summarize_list(episode_times)
    print("-" * 70)
    print("  局级：平均 %.0f ms/局，P50 %.0f，P95 %.0f" % (
        ep_summary["mean_ms"], ep_summary["p50_ms"], ep_summary["p95_ms"]))

    # 输出 JSON
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(args.output_dir, "bench_agent_%s_%s.json" % (args.device, timestamp))
    report = {
        "benchmark": "agent_decision",
        "device": args.device,
        "timestamp": timestamp,
        "episodes": args.episodes,
        "steps_per_episode": args.steps,
        "total_steps": len(all_latencies),
        "per_stage": per_stage,
        "episode_level": ep_summary,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n结果已写入: %s" % output_path)


if __name__ == "__main__":
    main()
