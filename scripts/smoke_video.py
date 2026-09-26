#!/usr/bin/env python3
"""第十四批 视频信息提取 mock 冒烟（CPU，无 GPU/联网/真实视频）。

链路：mock 下载 -> mock 抽帧 -> mock ASR 口播 -> mock VLM 图表
      -> 时间轴对齐 -> 转 SFT 问答对。

输出：
- data/video_raw/<BV>/meta.json、data/video_frames/<BV>/manifest.json（gitignored）；
- data/sft_data/video_sft_mock.jsonl（gitignored）；
- results/video_extract_report.txt 人工可读"视频信息提取报告"。

运行（仓库根）：python scripts/smoke_video.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from video_extract import load_video_config  # noqa: E402
from video_extract.downloader import MockDownloader  # noqa: E402
from video_extract.frame_extractor import MockFrameExtractor  # noqa: E402
from video_extract.transcriber import MockTranscriber  # noqa: E402
from video_extract.chart_reader import MockChartReader  # noqa: E402
from video_extract.aligner import align  # noqa: E402
from video_extract.structurer import build_sft, write_jsonl, format_timestamp  # noqa: E402

MOCK_URL = "https://www.bilibili.com/video/BV1MOCK00001"
SFT_OUT = os.path.join("data", "sft_data", "video_sft_mock.jsonl")


def main():
    print("=" * 72)
    print("arknights-llm-agent 视频信息提取 mock 冒烟（第十四批）")
    print("=" * 72)

    cfg = load_video_config()  # 冒烟固定走 mock，不读取 asr/vlx 真实 backend

    # 1) 下载 + 分类过滤（mock）。混一条"终末地"，验证它在下载前即被排除、不进后续流程。
    endfield_url = "https://www.bilibili.com/video/BV1MOCK00002"
    plan = {
        MOCK_URL: {"title": "【血狼破军】明日方舟危机合约干员输出与强度分析"},
        endfield_url: {"title": "血狼破军 明日方舟终末地对比实机演示"},
    }
    batch = MockDownloader(cfg).batch_download(list(plan.keys()), items=plan)
    # 断点续爬：已存在的明日方舟 meta 会进 skipped，它同样是放行项
    n_allowed = len(batch["downloaded"]) + len(batch["skipped"])
    assert n_allowed == 1 and len(batch["excluded"]) == 1, \
        "分类过滤应只放行 1 条明日方舟、排除 1 条终末地"
    meta = MockDownloader(cfg).download(MOCK_URL)  # 读取/复用该明日方舟 meta
    ex = batch["excluded"][0]
    print("[1/6] mock 下载+分类  放行 %d（%s，category=%s），排除 %d（%s -> %s）"
          % (n_allowed, meta.bv_id, meta.category,
             len(batch["excluded"]), ex["title"], ex["category"]))

    # 2) 抽帧（mock：manifest 占位时间戳，不生成图片）
    frames = MockFrameExtractor(cfg).extract(
        meta.bv_id, duration_sec=meta.duration_sec, video_path=meta.video_path)
    print("[2/6] mock 抽帧  %d 帧，时间戳 %s..%s（间隔 %ss，placeholder）"
          % (len(frames), frames[0].timestamp_sec, frames[-1].timestamp_sec,
             cfg["frames"]["interval_sec"]))

    # 3) ASR 口播
    transcript_path = os.path.join(cfg["download"]["out_dir"], meta.bv_id,
                                   "transcript.json")
    segs = MockTranscriber(cfg).transcribe(meta.audio_path, transcript_path)
    print("[3/6] mock ASR   %d 段口播" % len(segs))

    # 4) VLM 读图表
    charts_path = os.path.join(cfg["frames"]["out_root"], meta.bv_id, "charts.json")
    charts = MockChartReader(cfg).read_all(frames, charts_path)
    print("[4/6] mock VLM   %d 张图表：%s"
          % (len(charts), ", ".join("%s@%ss(%s)" %
                                    (c.chart_type, c.timestamp_sec, c.operator)
                                    for c in charts)))

    # 5) 对齐
    pairs = align(segs, charts, config=cfg)
    matched = sum(1 for p in pairs if p["matched"])
    print("[5/6] 时间轴对齐 %d 张图表，匹配口播 %d 张（容差 %ss）"
          % (len(pairs), matched, cfg["align"]["tolerance_sec"]))

    # 6) 转 SFT
    records = build_sft(pairs, meta, cfg)
    n = write_jsonl(records, SFT_OUT)
    print("[6/6] 转 SFT     %d 条 -> %s" % (n, SFT_OUT))

    # ---- 人工可读报告 ----
    lines = []
    lines.append("=" * 72)
    lines.append("视频信息提取报告（mock 全链路）")
    lines.append("=" * 72)
    lines.append("视频：%s" % meta.title)
    lines.append("来源：%s  UP主：%s  BV：%s  发布：%s"
                 % (meta.webpage_url, meta.uploader, meta.bv_id, meta.publish_time))
    lines.append("抽帧：%d 张（%s..%s，placeholder）"
                 % (len(frames), frames[0].timestamp_sec, frames[-1].timestamp_sec))
    lines.append("口播片段：%d；图表：%d；对齐匹配：%d/%d；SFT：%d 条"
                 % (len(segs), len(charts), matched, len(pairs), n))
    lines.append("-" * 72)
    lines.append("【口播时间轴】")
    for s in segs:
        lines.append("  %s-%s  %s" % (format_timestamp(s["start"]),
                                     format_timestamp(s["end"]), s["text"]))
    lines.append("-" * 72)
    lines.append("【图表 -> 就近口播】")
    for p in pairs:
        c = p["chart"]
        lines.append("  · %s @ %ss（%s）" %
                     (c["chart_type"], c["timestamp_sec"], c.get("operator", "")))
        if p["speech"]:
            lines.append("    口播 %s：%s（Δ=%ss，inferred:timestamp）"
                         % (format_timestamp(p["speech_start"]),
                            p["speech"]["text"], p["time_delta"]))
        else:
            lines.append("    口播：超出容差未匹配（不强行关联）")
    lines.append("-" * 72)
    lines.append("【SFT 样例】（evidence: chart/speech=retrieved，alignment=inferred）")
    for i, r in enumerate(records, 1):
        lines.append("  [%d] Q: %s" % (i, r["question"]))
        for ln in r["answer"].splitlines():
            lines.append("      %s" % ln)
        lines.append("      meta: %s"
                     % json.dumps(r["meta"], ensure_ascii=False, sort_keys=True))
        lines.append("")
    report = "\n".join(lines)
    print("\n" + report)

    os.makedirs("results", exist_ok=True)
    with open(os.path.join("results", "video_extract_report.txt"), "w",
              encoding="utf-8") as f:
        f.write(report + "\n")

    # 基本断言，保证冒烟真正跑通而非静默空转
    assert n == len(charts) == 2, "SFT/图表数量异常"
    assert matched == 2, "对齐应全部匹配"
    print("\n[run_smoke] video_extract mock 全链路通过")


if __name__ == "__main__":
    main()
