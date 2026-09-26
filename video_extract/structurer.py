"""把对齐后的"图表 + 口播"转成 SFT 问答对（CPU 真实实现）。

输出与 training/sft_data_prep.py 一致的 {"question", "answer", "meta"} JSONL：
- question：围绕视频对某干员的评价（输出能力 / 强度榜档位）；
- answer：先给"根据视频分析（UP主《标题》 BV号 mm:ss）"的来源，再列画面数字、
  口播要点与结论；明确这是 UP 主第三方分析，数字来自视频画面（retrieved），非官方事实；
- meta：source=video、BV 号、标题、UP 主、图表/口播时间戳、对齐时间差、证据分级。

证据分级（config.structure，可覆盖）：
- 画面数字 evidence_chart = retrieved:video_frame（参考资料：视频画面所示）
- 口播原文 evidence_speech = retrieved:video_audio（参考资料：UP 主观点）
- 时间轴就近关联 evidence_alignment = inferred:timestamp（推断）
"""

import json
import os

from . import DEFAULT_CONFIG_PATH, load_video_config

__all__ = ["build_sft", "build_record", "write_jsonl", "format_timestamp"]


def format_timestamp(sec):
    # type: (float) -> str
    try:
        sec = max(int(round(float(sec))), 0)
    except (TypeError, ValueError):
        sec = 0
    return "%02d:%02d" % (sec // 60, sec % 60)


def _as_dict(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return getattr(obj, "__dict__", {}) or {}


def _table_answer_lines(data):
    """从 table 类图表 data 抽取可读数值行。"""
    lines = []
    focus = data.get("focus") or {}
    if focus:
        bits = ["%s=%s" % (k, v) for k, v in focus.items() if k != "干员"]
        if bits:
            lines.append("画面数据表给出：%s。" % "，".join(bits))
    rows = data.get("rows") or []
    if not lines and rows:
        cols = data.get("columns") or (list(rows[0].keys()) if rows else [])
        for row in rows[:3]:
            bits = ["%s=%s" % (k, row.get(k)) for k in cols if k in row and k != "干员"]
            name = row.get("干员", "")
            if bits:
                lines.append("%s：%s。" % (name, "，".join(bits)))
    return lines


def _tier_answer_lines(data):
    lines = []
    focus = data.get("focus") or {}
    if focus.get("tier"):
        lines.append("画面强度榜将其列为 %s 档。" % focus.get("tier"))
    tiers = data.get("tiers") or {}
    if not lines and tiers:
        for tier in sorted(tiers.keys()):
            lines.append("%s：%s。" % (tier, "、".join(tiers[tier])))
    return lines


def build_record(pair, video_meta, cfg):
    """把一个对齐对（一张图表 + 就近口播）转成一条 SFT 记录；信息不足返回 None。"""
    chart = pair.get("chart") or {}
    ctype = chart.get("chart_type", "unknown")
    data = chart.get("data") or {}
    operator = chart.get("operator") or (data.get("focus") or {}).get("干员") or ""
    speech = pair.get("speech")
    s_cfg = cfg.get("structure", {})
    creator = s_cfg.get("creator_name", "UP主")
    ev_chart = s_cfg.get("evidence_chart", "retrieved:video_frame")
    ev_speech = s_cfg.get("evidence_speech", "retrieved:video_audio")
    ev_align = s_cfg.get("evidence_alignment", "inferred:timestamp")

    vm = _as_dict(video_meta)
    bv = vm.get("bv_id", "")
    title = vm.get("title", "")
    chart_ts = float(chart.get("timestamp_sec", 0.0))
    source_hint = "根据视频分析（%s《%s》，%s，画面 %s）：" % (
        creator, title, bv, format_timestamp(chart_ts))

    # ---- question / 数值行按图表类型分化 ----
    if ctype == "table":
        topic = "输出能力" if operator else "干员输出"
        question = "%s如何评价%s在危机合约中的%s？" % (
            creator, operator, topic) if operator else \
            "%s在视频中如何分析危机合约干员的输出？" % creator
        value_lines = _table_answer_lines(data)
        conclusion = "综合画面数据，%s认为其在本期环境输出表现突出。" % creator if operator else ""
    elif ctype == "tier_list":
        question = "%s在本期危机合约强度榜中把%s排在哪个档位？理由是什么？" % (
            creator, operator) if operator else \
            "%s在视频中给出的危机合约强度榜是怎样的？" % creator
        value_lines = _tier_answer_lines(data)
        conclusion = ""
    else:
        question = "%s在视频中对%s有怎样的分析？" % (creator, operator or "相关干员")
        value_lines = []
        conclusion = ""

    # ---- answer：来源 + 画面数字 + 口播要点 + 免责归因 ----
    ans = [source_hint.rstrip("：")]
    ans.extend(value_lines)
    if speech and speech.get("text"):
        ans.append("口播要点（%s）：%s" % (format_timestamp(speech.get("start", 0.0)),
                                       speech.get("text", "")))
    if conclusion:
        ans.append(conclusion)
    ans.append("（说明：以上为 %s 的第三方分析，数值取自视频画面、观点取自口播，"
               "经时间戳就近关联，仅作训练参考，非 PRTS/官方结论。）" % creator)
    answer = "\n".join(x for x in ans if x)

    record = {
        "question": question,
        "answer": answer,
        "meta": {
            "source": "video",
            "bv_id": bv,
            "video_title": title,
            "uploader": vm.get("uploader", creator),
            "chart_type": ctype,
            "operator": operator,
            "timestamps": {
                "chart": round(chart_ts, 3),
                "speech_start": pair.get("speech_start"),
                "speech_end": pair.get("speech_end"),
                "time_delta": pair.get("time_delta"),
            },
            "speech_matched": bool(pair.get("matched")),
            "evidence": {
                "chart": ev_chart,
                "speech": ev_speech if speech else None,
                "alignment": ev_align if pair.get("matched") else ev_align + "(unmatched)",
            },
        },
    }
    return record


def build_sft(aligned_pairs, video_meta, config=None, config_path=DEFAULT_CONFIG_PATH):
    """对所有对齐对生成 SFT 记录；空输入安全返回 []。"""
    cfg = config or load_video_config(config_path)
    records = []
    for pair in aligned_pairs or []:
        rec = build_record(pair, video_meta, cfg)
        if rec is not None:
            records.append(rec)
    return records


def write_jsonl(records, path):
    """写 JSONL（ensure_ascii=False）；自动建目录，返回写入条数。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(records)
