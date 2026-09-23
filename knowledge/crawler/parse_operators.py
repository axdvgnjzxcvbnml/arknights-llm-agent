"""干员页解析：从 PRTS Wiki 干员页 HTML 提取结构化干员数据。

真实页面结构（样本：阿米娅）：
- 元数据：<script> 中 var char_info = {name, nameEn, star, group, class, branch, pos, tag, ...}
- 章节：特性 / 获得方式 / 属性 / 天赋 / 潜能提升 / 技能 / ...
- 属性章节：char-extra-attr-table（再部署/费用/阻挡/间隔/势力）+
  char-base-attr-table（四阶段成长属性：精英0 1级~精英2 满级 + 信赖加成上限）
- 技能章节：每个技能两张重复表格（nomobile 桌面版 / nodesktop 移动版），只解析 nomobile 版；
  行结构 = 等级(1-7/Rank Ⅰ-Ⅲ) | 描述 | 初始 | 消耗 | 持续
"""

import re

from ._html_utils import (
    extract_js_object,
    get_section,
    iter_section_tables,
    parse_html,
    table_rows,
    th_td_pairs,
)

__all__ = ["parse_operator"]


def _parse_meta(soup):
    """从 char_info JS 对象提取干员元数据。

    注意：PRTS 的 star 字段为 0 基编码（star = 真实星级 - 1），
    例：芬 3 星 star=2，拉普兰德 5 星 star=4，能天使 6 星 star=5。
    因此额外输出 star_rating = star + 1 表示游戏内星级。
    """
    meta = {}
    for script in soup.find_all("script"):
        text = script.string or ""
        if "var char_info" in text:
            info = extract_js_object(text, "char_info")
            for key in ("name", "nameEn", "group", "class", "branch", "pos", "tag"):
                if key in info:
                    meta[key] = info[key]
            if isinstance(info.get("star"), int):
                meta["star"] = info["star"]
                meta["star_rating"] = info["star"] + 1
            break
    return meta


def _parse_trait(soup):
    """特性（id=特性 章节第一张表）。

    真实行结构存在两种布局：
    1. 表头 ['分支','描述']，下一数据行直接是值
       [分支名, 特性描述]（如 ['速射手','优先攻击空中单位']）；
    2. 表头 ['分支','条件']（条件式特性，如猎手/链术师），首行 [分支名,'精英阶段0']，
       其后每行 [精英阶段N, 该阶段特性描述]。
    两种布局后均可能跟 ['分支信息'] 标签行与单独一行的说明文本。
    """
    tables = list(iter_section_tables(soup, "特性"))
    if not tables:
        return {}
    rows = table_rows(tables[0])
    data = {}
    header_idx = next(
        (i for i, row in enumerate(rows) if row[:2] in (["分支", "描述"], ["分支", "条件"])),
        None,
    )
    if header_idx is not None and header_idx + 1 < len(rows):
        header = rows[header_idx]
        value_row = rows[header_idx + 1]
        if len(value_row) >= 1:
            data["分支"] = value_row[0]
        if header[:2] == ["分支", "描述"] and len(value_row) >= 2:
            data["描述"] = value_row[1]
        else:
            # 条件式：收集 [阶段, 描述] 行，拼成一段可检索文本
            parts = []
            for row in rows[header_idx + 2:]:
                if len(row) == 1 and row[0] == "分支信息":
                    break
                if len(row) >= 2 and row[0] and row[1]:
                    parts.append("%s：%s" % (row[0], row[1]))
            if parts:
                data["描述"] = "；".join(parts)
    for i, row in enumerate(rows):
        if len(row) == 1 and row[0] == "分支信息" and i + 1 < len(rows) and rows[i + 1]:
            data["分支信息"] = rows[i + 1][0]
    return data


def _parse_obtain(soup):
    """获得方式（id=获得方式 章节）。"""
    tables = list(iter_section_tables(soup, "获得方式"))
    if not tables:
        return {}
    return th_td_pairs(tables[0])


def _parse_extra_attrs(soup):
    """基础属性（char-extra-attr-table）：再部署时间/初始部署费用/阻挡数/攻击间隔/所属势力/隐藏势力。"""
    for table in iter_section_tables(soup, "属性"):
        cls = " ".join(table.get("class") or [])
        if "char-extra-attr-table" in cls:
            return th_td_pairs(table)
    return {}


def _parse_growth_attrs(soup):
    """成长属性（char-base-attr-table）：生命上限/攻击/防御/法术抗性 的 精英0~精英2 + 信赖加成。"""
    for table in iter_section_tables(soup, "属性"):
        cls = " ".join(table.get("class") or [])
        if "char-base-attr-table" in cls:
            rows = table_rows(table)
            if not rows:
                return {}
            header = rows[0]
            result = {"stages": [h for h in header if h], "rows": {}}
            for row in rows[1:]:
                if not row:
                    continue
                name = row[0]
                result["rows"][name] = row[1:]
            return result
    return {}


def _parse_skills(soup):
    """技能列表：解析 nomobile 版本的技能表（排除后勤技能/技能升级等非技能表）。"""
    skills = []
    for table in iter_section_tables(soup, "技能"):
        cls = " ".join(table.get("class") or [])
        if "nomobile" not in cls:
            continue
        rows = table_rows(table)
        if len(rows) < 3:
            continue
        # 首行 = [图标空列, 技能名, 类型说明...]，取前两个非空 cell
        name_row = [c for c in rows[0] if c]
        if len(name_row) < 2:
            continue
        skill_name = name_row[0]
        skill_type = name_row[1]
        # 第二行是表头（等级/描述/初始/消耗/持续）
        if len(rows[1]) < 3 or rows[1][0] != "等级":
            continue
        levels = []
        for row in rows[2:]:
            if len(row) >= 5:
                levels.append(
                    {
                        "level": row[0],
                        "desc": row[1],
                        "initial": row[2],
                        "cost": row[3],
                        "duration": row[4],
                    }
                )
        if levels:
            skills.append({"name": skill_name, "type": skill_type, "levels": levels})
    return skills


def parse_operator(html):
    # type: (str) -> dict
    """解析干员页 HTML，返回结构化干员数据（dict，可直接 JSON 序列化）。"""
    soup = parse_html(html)
    operator = {
        "name": "",
        "meta": _parse_meta(soup),
        "trait": _parse_trait(soup),
        "obtain": _parse_obtain(soup),
        "extra_attrs": _parse_extra_attrs(soup),
        "growth_attrs": _parse_growth_attrs(soup),
        "skills": _parse_skills(soup),
    }
    operator["name"] = operator["meta"].get("name", "")
    return operator
