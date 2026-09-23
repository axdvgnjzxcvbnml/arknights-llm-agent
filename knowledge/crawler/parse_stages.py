"""关卡页解析：从 PRTS Wiki 关卡页 HTML 提取结构化关卡数据。

真实页面结构（样本：3-8）：
- 章节：剧情 / 普通 / 突袭 / 敌方情报 / 模组任务 / 材料掉落 / 注释与链接
- 普通/突袭章节第一张 wikitable = 关卡信息卡：
  首行 = 关卡名；次行 = 关卡描述；其余行为键值字段
  （解锁条件 / 推荐等级 / 作战消耗 / 部署上限+初始COST+COST上限 /
   目标点耐久+待处理目标数量+最短用时 / 掉落 / 特殊地形效果 / 地图）
- 敌方情报章节：stage-enemy-table，表头 = 头像/名称/数量/地位/级别/生命值/攻击力/
  防御力/法术抗性/攻击间隔/元素抗性/损伤抵抗/重量等级/移动速度/攻击半径/目标价值
"""

import re

from ._html_utils import get_section, parse_html, table_rows

__all__ = ["parse_stage"]


def _iter_tables(nodes):
    """遍历章节节点中的所有表格（节点本身是 table 时也要包含）。"""
    for node in nodes:
        if node.name == "table":
            yield node
        else:
            for table in node.find_all("table"):
                yield table


def _parse_mode(soup, mode_id):
    """解析普通/突袭模式的关卡信息卡（th/td 跨行配对，实测结构见模块 docstring）。"""
    nodes = get_section(soup, mode_id)
    for table in _iter_tables(nodes):
        cls = " ".join(table.get("class") or [])
        if "navbox" in cls:
            continue
        trs = table.find_all("tr")
        if len(trs) < 2:
            continue
        info = {}

        def _cells(tr):
            return [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]

        # 首行：关卡名；次行：描述
        first = _cells(trs[0])
        if first:
            info["name"] = first[0]
        second = _cells(trs[1])
        if second:
            info["desc"] = second[0]

        # 其余行：字段行(全 th) 与数值行(全 td) 跨行配对；同行 th/td 直接配对
        pending = []
        for tr in trs[2:]:
            ths = [re.sub(r"\s+", " ", t.get_text(" ", strip=True)) for t in tr.find_all("th")]
            tds = [re.sub(r"\s+", " ", t.get_text(" ", strip=True)) for t in tr.find_all("td")]
            if ths and tds:
                for k, v in zip(ths, tds):
                    if k:
                        info[k] = v
            elif tds and pending:
                for k, v in zip(pending, tds):
                    if k:
                        info[k] = v
                pending = []
            elif ths:
                pending = list(ths)
        return info
    return {}


def _parse_enemies(soup):
    """敌方情报章节：敌人列表（表格首行为章节标题"敌方情报"，第二行才是表头）。"""
    nodes = get_section(soup, "敌方情报")
    enemies = []
    for table in _iter_tables(nodes):
        cls = " ".join(table.get("class") or [])
        if "stage-enemy-table" not in cls:
            continue
        rows = table_rows(table)
        if len(rows) < 3:
            continue
        # 找到真正的表头行（包含"名称"列）
        header = None
        data_start = None
        for i, row in enumerate(rows):
            if "名称" in row:
                header = row
                data_start = i + 1
                break
        if header is None:
            continue
        for row in rows[data_start:]:
            if len(row) < len(header):
                continue
            enemies.append(dict(zip(header, row)))
    return enemies


def parse_stage(html):
    # type: (str) -> dict
    """解析关卡页 HTML，返回结构化关卡数据（dict，可直接 JSON 序列化）。"""
    soup = parse_html(html)
    # 关卡编号（页面标题，如 "3-8 - PRTS - ..."）
    title = (soup.title.string or "") if soup.title else ""
    code = title.split()[0].strip() if title else ""
    stage = {
        "code": code,
        "normal": _parse_mode(soup, "普通"),
        "raid": _parse_mode(soup, "突袭"),
        "enemies": _parse_enemies(soup),
    }
    return stage
