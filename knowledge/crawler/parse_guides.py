"""攻略文本生成：从已解析的干员/敌人/关卡 JSON 生成可检索的攻略文本片段。

背景（2026-09 探查结论）：PRTS Wiki 为数据百科，站内无独立"攻略"页面
（api 搜索 totalhits=0）。可用于决策的攻略性内容 = 敌方情报 + 关卡信息 +
干员特性/技能描述。本模块把结构化 JSON 转成自然语言文本块，供 RAG 索引。

输出格式：list[dict] = [{"title": str, "text": str}, ...]
"""

__all__ = ["build_guides", "operator_to_guide", "enemy_to_guide", "stage_to_guide"]


def operator_to_guide(op):
    # type: (dict) -> dict
    """干员 JSON -> 攻略文本块。"""
    meta = op.get("meta", {})
    lines = []
    lines.append(
        "干员%s：%s干员，分支%s，攻击位置%s，标签%s。"
        % (
            op.get("name", ""),
            meta.get("class", "未知"),
            meta.get("branch", "未知"),
            meta.get("pos", "未知"),
            meta.get("tag", "未知"),
        )
    )
    trait = op.get("trait", {})
    if trait.get("描述"):
        lines.append("特性：%s。" % trait["描述"])
    skills = op.get("skills", [])
    if skills:
        skill_parts = []
        for s in skills[:3]:
            desc = ""
            if s.get("levels"):
                desc = s["levels"][0].get("desc", "")
            skill_parts.append("%s（%s：%s）" % (s.get("name", ""), s.get("type", ""), desc))
        lines.append("技能：" + "；".join(skill_parts) + "。")
    return {"title": "干员攻略_%s" % op.get("name", ""), "text": "\n".join(lines)}


def enemy_to_guide(enemy):
    # type: (dict) -> dict
    """敌人 JSON -> 攻略文本块（含各等级属性）。"""
    lines = []
    for lv in enemy.get("levels", []):
        d = lv.get("data", {})
        parts = []
        for key in (
            "地位",
            "种类",
            "描述",
            "攻击方式",
            "行动方式",
            "最大生命值",
            "攻击力",
            "防御力",
            "法术抗性",
            "攻击半径",
            "重量",
            "移动速度",
            "攻击间隔",
            "目标价值",
        ):
            if d.get(key):
                parts.append("%s%s" % (key, d[key]))
        attrs = "，".join(parts) if parts else "无属性数据"
        lines.append("级别%s：%s" % (lv.get("level", ""), attrs))
    return {
        "title": "敌人攻略_%s" % enemy.get("name", ""),
        "text": "敌人%s。%s" % (enemy.get("name", ""), "；".join(lines)),
    }


def stage_to_guide(stage):
    # type: (dict) -> dict
    """关卡 JSON -> 攻略文本块（关卡信息 + 敌方情报）。"""
    lines = []
    normal = stage.get("normal", {})
    code = stage.get("code", "")
    name = normal.get("name", "")
    lines.append("关卡%s（%s）" % (code, name))
    if normal.get("desc"):
        lines.append("描述：%s。" % normal["desc"])
    for key in ("解锁条件", "推荐等级", "作战消耗", "部署上限", "目标点耐久", "特殊地形效果"):
        if normal.get(key):
            lines.append("%s：%s" % (key, normal[key]))
    enemies = stage.get("enemies", [])
    if enemies:
        enemy_parts = []
        for e in enemies:
            enemy_parts.append(
                "%s×%s（%s级%s）" % (e.get("名称", ""), e.get("数量", ""), e.get("级别", ""), e.get("地位", ""))
            )
        lines.append("敌人配置：" + "，".join(enemy_parts) + "。")
    return {"title": "关卡攻略_%s_%s" % (code, name), "text": "\n".join(lines)}


def build_guides(operators, enemies, stages):
    # type: (list, list, list) -> list
    """批量生成攻略文本块。"""
    guides = []
    for op in operators:
        guides.append(operator_to_guide(op))
    for enemy in enemies:
        guides.append(enemy_to_guide(enemy))
    for stage in stages:
        guides.append(stage_to_guide(stage))
    return guides
