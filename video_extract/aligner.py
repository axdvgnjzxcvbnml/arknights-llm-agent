"""口播↔画面时间轴对齐（CPU 真实实现，纯函数，无外部依赖）。

把"画面在 ts 显示某图表"与"该时刻口播在说什么"关联：
- 优先选时间区间包含该时间戳的口播片段；
- 否则按"图表时间戳 ↔ 口播片段中点"就近匹配；
- 最近距离仍超过 tolerance，则该图表 matched=False、speech=None（不强行配错）。

注意：时间戳就近关联是推断（evidence=inferred:timestamp），不是语义级对齐，
真机阶段可再用 VAD/字幕做更精确校准。
"""

from . import DEFAULT_CONFIG_PATH, load_video_config

__all__ = ["align", "nearest_speech"]


def _as_dict(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return getattr(obj, "__dict__", None)


def _segments(transcript):
    out = []
    for s in transcript or []:
        d = _as_dict(s)
        if d is None:
            continue
        try:
            start = float(d.get("start", 0.0))
            end = float(d.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end < start:
            start, end = end, start
        out.append({"start": start, "end": end, "text": d.get("text", ""),
                    "mid": (start + end) / 2.0})
    return out


def nearest_speech(timestamp_sec, transcript, tolerance=8.0):
    """返回 (speech_dict_or_None, signed_delta, matched)。

    delta = 图表时间戳 - 口播片段中点（负=口播在前，正=口播在后）。
    """
    segs = _segments(transcript)
    if not segs:
        return None, None, False
    ts = float(timestamp_sec)

    # 1) 区间包含
    containing = [s for s in segs if s["start"] <= ts <= s["end"]]
    if containing:
        # 多个命中时取中点最近的（通常只有一个）
        best = min(containing, key=lambda s: abs(ts - s["mid"]))
        return {"start": best["start"], "end": best["end"], "text": best["text"]}, \
            round(ts - best["mid"], 3), True

    # 2) 中点就近
    best = min(segs, key=lambda s: abs(ts - s["mid"]))
    delta = round(ts - best["mid"], 3)
    if abs(delta) > float(tolerance):
        return None, delta, False
    return {"start": best["start"], "end": best["end"], "text": best["text"]}, delta, True


def align(transcript, charts, tolerance=None, config=None,
          config_path=DEFAULT_CONFIG_PATH):
    """对每张图表就近匹配口播片段。

    返回 [{"chart": chart_dict, "speech": seg_dict|None, "speech_start",
           "speech_end", "time_delta", "matched": bool}, ...]，顺序同 charts。
    """
    if tolerance is None:
        cfg = config or load_video_config(config_path)
        tolerance = float(cfg.get("align", {}).get("tolerance_sec", 8.0))

    pairs = []
    for c in charts or []:
        chart = _as_dict(c)
        if chart is None:
            continue
        ts = float(chart.get("timestamp_sec", 0.0))
        speech, delta, matched = nearest_speech(ts, transcript, tolerance)
        pairs.append({
            "chart": chart,
            "speech": speech,
            "speech_start": speech["start"] if speech else None,
            "speech_end": speech["end"] if speech else None,
            "time_delta": delta,
            "matched": matched,
        })
    return pairs
