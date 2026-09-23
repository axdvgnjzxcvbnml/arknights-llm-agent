# 纯 CPU、无模型依赖：把结构化 GameState(+可选 VLMAnalysis) 渲染成高密度中文文本喂 LLM。
"""结构化游戏状态 -> 自然语言状态报告。

设计目标：信息密度高、分区固定、不啰嗦、不漏关键字段；每个可能"看错/估算/推断"的量都
带来源分级标签，方便 LLM 判断可信度。空状态安全（返回占位报告，不抛异常）。

来源/证据标签：
- [CV确认] 视觉确认；[计时估算] 均匀估算；[标注时间轴] 人工/录制标注；[VLM] VLM 判断。
- 证据分级区统一汇总 fact / retrieved / inferred / cv / estimated。
"""

from typing import List, Optional

from .schemas import GameState, VLMAnalysis

__all__ = ["state_to_text", "SOURCE_LABELS"]

# SpawnSource / ReadingSource -> 中文短标签
SOURCE_LABELS = {
    "cv": "CV确认",
    "timer:estimated": "计时估算",
    "timer:annotated": "标注时间轴",
    "vlm": "VLM",
    "mock": "mock",
    "manual": "人工",
}

_DIRECTION_CN = {"up": "上", "down": "下", "left": "左", "right": "右"}
_TIMING_CN = {"annotated": "标注时间轴", "estimated": "计时估算(estimated)", "none": "无"}


def _src_label(source):
    return SOURCE_LABELS.get(source, str(source or "未知"))


def _cost_text(cost):
    if cost is None:
        return "未知"
    base = "费用 %d" % cost.current
    if cost.limit is not None:
        base += "/%d" % cost.limit
    if cost.state == "uncertain":
        base += " [存疑:相邻帧读数不一致,暂勿据此决策]"
    elif cost.state == "missing":
        base += " [本帧未读到,沿用上次值]"
    else:
        base += " [稳定]"
    return base + "(%s)" % _src_label(cost.source)


def _cards_text(cards):
    if not cards:
        return "无"
    parts = []
    for c in cards:
        s = "%s(%s,%d费" % (c.name, c.operator_class or "未知职业", c.cost)
        s += ",可部署)" if c.available else ",暂不可用)"
        parts.append(s)
    return "、".join(parts)


def _deployed_and_skills(state):
    # type: (GameState) -> List[str]
    lines = []
    if state.deployed:
        for d in state.deployed:
            hp = "" if d.hp_ratio is None else " HP%d%%" % round(d.hp_ratio * 100)
            lines.append("- %s@%s朝%s%s" % (
                d.name, d.cell_id or "?", _DIRECTION_CN.get(d.direction, d.direction), hp))
    else:
        lines.append("- 无已部署干员")
    if state.skills:
        for sk in state.skills:
            if sk.active:
                status = "生效中"
            elif sk.ready:
                status = "可开启"
            else:
                status = "充能中"
            extra = (" %s" % sk.sp_text) if sk.sp_text else ""
            lines.append("  技能 %s-S%d%s %s(%s)" % (
                sk.operator or "?", sk.slot + 1, extra, status, _src_label(sk.source)))
    return lines


def _enemy_lines(state):
    # type: (GameState) -> List[str]
    lines = []
    if state.enemies_on_field:
        for e in state.enemies_on_field:
            hint = ("%s " % e.position_hint) if e.position_hint else ""
            lines.append("- %s%s x%d [%s]" % (
                hint, e.name, e.observed_count, _src_label(e.source)))
    else:
        lines.append("- 当前场上无已到点敌人")
    # 波次构成（含未到点），让 LLM 看到全貌与时间
    pending = [p for p in state.spawn_plan]
    if pending:
        comp = "、".join("%s x%d@t=%.0fs[%s]" % (
            p.enemy, p.count, p.expected_time_sec,
            "CV确认" if p.appeared else _src_label(p.confirmed_by))
            for p in pending)
        lines.append("波次构成: " + comp)
    return lines


def _map_text(game_map):
    if game_map is None:
        return "未知"
    ids = game_map.deployable_ids()
    head = "%dx%d 可部署%d格" % (game_map.cols, game_map.rows, len(ids))
    if ids:
        return head + ": " + " ".join(ids)
    return head + "（当前无空格）"


def _evidence_section(state, analysis):
    # type: (GameState, Optional[VLMAnalysis]) -> List[str]
    buckets = {"fact": [], "retrieved": [], "inferred": [], "cv": [],
               "estimated": [], "annotated": [], "mock": []}

    if state.cost is not None and state.cost.state != "missing":
        buckets["cv" if state.cost.source == "cv" else "mock"].append(
            "费用读数(%s)" % _src_label(state.cost.source))
    for e in state.enemies_on_field:
        tag = {"cv": "cv", "timer:estimated": "estimated",
               "timer:annotated": "annotated", "vlm": "inferred"}.get(e.source)
        if tag:
            buckets[tag].append("%s x%d 出现" % (e.name, e.observed_count))
    if state.timing_source == "estimated":
        buckets["estimated"].append("敌人出场时间为均匀估算(非精确波次)")
    elif state.timing_source == "annotated":
        buckets["annotated"].append("敌人出场时间来自录制标注时间轴")

    if analysis is not None:
        buckets["inferred"].append("VLM 局势判断与建议(%s)" % _src_label(analysis.analyzer))
        for ref in analysis.evidence:
            buckets[ref.evidence].append("%s: %s" % (ref.source or "未知来源", ref.detail))

    title = {
        "fact": "fact(PRTS结构化事实)",
        "retrieved": "retrieved(RAG参考资料,需核实)",
        "inferred": "inferred(规则/模型推断,非事实)",
        "cv": "cv(视觉确认)",
        "estimated": "estimated(均匀估算值)",
        "annotated": "annotated(录制标注)",
        "mock": "mock(程序合成数据,非真实画面)",
    }
    lines = []
    for key in ("fact", "retrieved", "inferred", "cv", "estimated", "annotated", "mock"):
        if buckets[key]:
            lines.append("- %s: %s" % (title[key], "；".join(dict.fromkeys(buckets[key]))))
    if not lines:
        lines.append("- （无）")
    return lines


def state_to_text(state, analysis=None):
    # type: (Optional[GameState], Optional[VLMAnalysis]) -> str
    """渲染状态报告。state 为 None/空时返回安全占位文本。"""
    if state is None:
        return "【游戏状态】暂无视觉状态数据。"

    L = []  # type: List[str]
    stage = state.stage_id or "未知关卡"
    L.append("【关卡】%s | t=%.1fs | 波次时间轴: %s" % (
        stage, state.timestamp, _TIMING_CN.get(state.timing_source, state.timing_source)))

    resource = _cost_text(state.cost)
    if state.life_points is not None or state.deploy_limit is not None:
        resource += " | 耐久 %s" % (state.life_points if state.life_points is not None else "?")
        if state.deploy_limit is not None:
            used = state.deploy_used if state.deploy_used is not None else 0
            resource += " | 部署 %d/%d" % (used, state.deploy_limit)
    L.append("【资源】" + resource)

    L.append("【可用干员】" + _cards_text(state.operator_cards))

    L.append("【已部署/技能】")
    L.extend("  " + x for x in _deployed_and_skills(state))

    L.append("【敌情波次】")
    L.extend("  " + x for x in _enemy_lines(state))

    L.append("【地图】" + _map_text(state.game_map))

    if analysis is not None:
        L.append("【VLM局势】(%s,置信度%.2f) %s" % (
            _src_label(analysis.analyzer), analysis.confidence,
            analysis.situation or "（无）"))
        if analysis.strategic_advice:
            L.append("【VLM建议】" + analysis.strategic_advice)
        # 只展示与 state.notes 不重复的 VLM 风险，避免同一条估算说明出现两次
        extra_risks = [r for r in analysis.risks if r not in state.notes]
        if extra_risks:
            L.append("【风险/备注】" + "；".join(extra_risks))

    # 状态自身的备注（即使没有 VLM 也要透出估算说明）
    if state.notes:
        L.append("【备注】" + "；".join(state.notes))

    L.append("【证据分级】")
    L.extend("  " + x for x in _evidence_section(state, analysis))
    return "\n".join(L)
