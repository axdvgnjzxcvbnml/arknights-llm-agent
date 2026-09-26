#!/usr/bin/env python3
"""视觉解析各模块延迟基准（mock）：screen_capture / OCR / map_parser /
state_parser / detector_yolo / state_to_text / vlm_analyzer。

用 mock 实现测量各模块的处理延迟。V100 上替换为真实模型后重跑对比。

用法：
    python scripts/bench_perception.py --device cpu --runs 50
    python scripts/bench_perception.py --device gpu  # V100 上用真实 YOLO/VLM

输出：
    results/benchmarks/bench_perception_<device>_<timestamp>.json
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from perception.screen_capture import MockScreenCapture  # noqa: E402
from perception.ocr_cost import MockOCRCostReader  # noqa: E402
from perception.map_parser import MockMapParser  # noqa: E402
from perception.state_parser import StateParser  # noqa: E402
from perception.detector_yolo import MockDetector  # noqa: E402
from perception.state_to_text import state_to_text  # noqa: E402
from perception.vlm_analyzer import MockVLMAnalyzer  # noqa: E402
from perception.schemas import (  # noqa: E402
    CostStatus, EnemyPresence, GameMap, GameState,
    GridCell, OperatorCard, SkillStatus,
)


def _make_mock_state():
    """构造一个完整的 mock GameState（用于 state_to_text 和 vlm benchmark）。"""
    return GameState(
        stage_id="3-8",
        cost=CostStatus(current=15, state="ok"),
        operator_cards=[
            OperatorCard(name="芬", operator_class="先锋", cost=2, slot=0),
            OperatorCard(name="克洛丝", operator_class="狙击", cost=3, slot=1),
        ],
        deployed=[],
        skills=[SkillStatus(operator="芬", slot=0, ready=True)],
        enemies_on_field=[EnemyPresence(name="冲锋兵", observed_count=3, position_hint="左侧")],
        game_map=GameMap(cols=10, rows=8, cells=[
            GridCell(cell_id="C3", col=2, row=2, deployable=True, occupied=False),
        ]),
    )


def percentile(data, p):
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1 if f + 1 < len(s) else f
    return s[f] + (s[c] - s[f]) * (k - f)


def summarize(latencies):
    return {
        "samples": len(latencies),
        "mean_ms": round(statistics.mean(latencies), 3),
        "p50_ms": round(percentile(latencies, 50), 3),
        "p95_ms": round(percentile(latencies, 95), 3),
        "min_ms": round(min(latencies), 3),
        "max_ms": round(max(latencies), 3),
    }


def bench(name, fn, runs, setup_fn=None):
    """跑一个函数 N 次，返回延迟列表。"""
    if setup_fn:
        setup_fn()
    latencies = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        latencies.append((time.perf_counter() - t0) * 1000.0)
    return latencies


def main():
    parser = argparse.ArgumentParser(description="视觉解析模块延迟基准")
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--output-dir", default="results/benchmarks")
    args = parser.parse_args()

    print("视觉解析基准：device=%s，每个模块 %d 次" % (args.device, args.runs))

    # 初始化 mock 组件
    screen = MockScreenCapture()
    ocr = MockOCRCostReader()
    map_parser = MockMapParser()
    detector = MockDetector()
    vlm = MockVLMAnalyzer()
    state_parser = StateParser()

    # 预热
    frame = screen.capture()
    ocr.read(frame)
    map_parser.parse(frame)
    detector.detect(frame)

    results = {}

    # 1. screen_capture
    print("  跑 screen_capture...", end="\r")
    lat = bench("screen_capture", screen.capture, args.runs)
    results["screen_capture"] = summarize(lat)

    # 2. ocr_cost
    print("  跑 ocr_cost...      ", end="\r")
    lat = bench("ocr_cost", lambda: ocr.read(frame), args.runs)
    results["ocr_cost"] = summarize(lat)

    # 3. map_parser
    print("  跑 map_parser...    ", end="\r")
    lat = bench("map_parser", lambda: map_parser.parse(frame), args.runs)
    results["map_parser"] = summarize(lat)

    # 4. detector_yolo (mock)
    print("  跑 detector_yolo... ", end="\r")
    lat = bench("detector_yolo", lambda: detector.detect(frame), args.runs)
    results["detector_yolo_mock"] = summarize(lat)

    # 5. state_parser（组装完整状态，纯CPU组装）
    print("  跑 state_parser...  ", end="\r")
    mock_state = _make_mock_state()
    def run_state_parser():
        cost = ocr.read(frame)
        game_map = map_parser.parse(frame)
        return state_parser.assemble(
            stage_id="3-8", timestamp=0.0,
            cost=cost, game_map=game_map,
            operator_cards=mock_state.operator_cards,
            deployed=mock_state.deployed,
            skills=mock_state.skills,
            enemies_on_field=mock_state.enemies_on_field)
    lat = bench("state_parser", run_state_parser, args.runs)
    results["state_parser"] = summarize(lat)

    # 6. state_to_text
    print("  跑 state_to_text... ", end="\r")
    test_state = run_state_parser()
    lat = bench("state_to_text", lambda: state_to_text(test_state), args.runs)
    results["state_to_text"] = summarize(lat)

    # 7. vlm_analyzer (mock)
    print("  跑 vlm_analyzer...  ", end="\r")
    lat = bench("vlm_analyzer", lambda: vlm.analyze(frame, test_state), args.runs)
    results["vlm_analyzer_mock"] = summarize(lat)

    # 打印汇总
    print("\n" + "=" * 70)
    print("  %-20s  %8s  %8s  %8s  %8s" % (
        "模块", "P50(ms)", "P95(ms)", "平均(ms)", "最大(ms)"))
    print("=" * 70)
    for name, summary in results.items():
        print("  %-20s  %8.3f  %8.3f  %8.3f  %8.3f" % (
            name, summary["p50_ms"], summary["p95_ms"],
            summary["mean_ms"], summary["max_ms"]))

    # 快通道总延迟（screen + ocr + map + detector + state_parser）
    fast_total = sum(results[k]["mean_ms"] for k in
                     ["screen_capture", "ocr_cost", "map_parser",
                      "detector_yolo_mock", "state_parser"])
    print("-" * 70)
    print("  快通道合计（截屏+OCR+地图+检测+状态组装）：%.2f ms" % fast_total)
    print("  慢通道（VLM mock）：%.2f ms" % results["vlm_analyzer_mock"]["mean_ms"])

    # 输出 JSON
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(args.output_dir, "bench_perception_%s_%s.json" % (args.device, timestamp))
    report = {
        "benchmark": "perception_modules",
        "device": args.device,
        "timestamp": timestamp,
        "runs_per_module": args.runs,
        "modules": results,
        "fast_channel_total_ms": round(fast_total, 3),
        "slow_channel_mock_ms": round(results["vlm_analyzer_mock"]["mean_ms"], 3),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n结果已写入: %s" % output_path)


if __name__ == "__main__":
    main()
