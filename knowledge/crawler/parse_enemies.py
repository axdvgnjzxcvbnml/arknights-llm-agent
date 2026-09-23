"""敌人页解析：从 PRTS Wiki 敌人页 HTML 提取结构化敌人数据。

真实页面结构（样本：源石虫）：
- 章节：级别0 / 级别1 / ... / 敌人模型（每级一张 enemy-info-level 表）
- enemy-info-level 表结构（th/td 跨行配对）：
  名称 | 地位 | 种类
  描述
  攻击方式 | 行动方式
  属性表：生命自回速度 / 最大生命值 / 攻击力 / 防御力 / 法术抗性 / 攻击半径 / 重量 /
          移动速度 / 攻击间隔 / 元素抗性 / 损伤抵抗 / 基础嘲讽等级 / 目标价值
  特性
"""

import re

from ._html_utils import get_section, parse_html, th_td_pairs

__all__ = ["parse_enemy"]

# 敌人属性字段白名单：PRTS 表头常带注释（如"地位 战斗中所使用的数据"），按前缀归并
_ENEMY_FIELDS = (
    "名称",
    "地位",
    "种类",
    "描述",
    "攻击方式",
    "行动方式",
    "生命自回速度",
    "最大生命值",
    "攻击力",
    "防御力",
    "法术抗性",
    "攻击半径",
    "重量",
    "移动速度",
    "攻击间隔",
    "元素抗性",
    "损伤抵抗",
    "基础嘲讽等级",
    "目标价值",
    "特性",
)


def _clean_enemy_data(data):
    """把带注释的字段名（如"地位 战斗中所使用的数据"）归并为白名单字段名。"""
    out = {}
    for k, v in data.items():
        key = k
        for f in _ENEMY_FIELDS:
            if k.startswith(f):
                key = f
                break
        out[key] = v
    return out


def _parse_traits(table, data):
    """特性提取，兼容两种实测结构：
    1) 表格 th/td 配对结果中含特性类字段（如"特性"/"异常抗性"）；—— 碎骨等 boss
    2) 末尾无表头的整行 td（colspan）内 <i> 斜体文本；—— 源石虫等普通敌人
    """
    for key in ("特性", "异常抗性", "天赋"):
        value = data.get(key)
        if value:
            if isinstance(value, list):
                return value
            return [value]
    trs = table.find_all("tr")
    if not trs:
        return []
    for td in trs[-1].find_all("td"):
        items = [i.get_text(" ", strip=True) for i in td.find_all("i")]
        items = [x for x in items if x]
        if items:
            return items
    return []


def _section_id_to_level(soup):
    """收集页面中所有"级别N"章节标题。"""
    levels = []
    for h2 in soup.find_all("h2"):
        sid = h2.get("id", "")
        m = re.match(r"^级别(\d+)$", sid)
        if m:
            levels.append(int(m.group(1)))
    return sorted(levels)


def _parse_level(soup, level):
    """解析单个级别章节（enemy-info-level 表）。"""
    nodes = get_section(soup, "级别%d" % level)
    for node in nodes:
        tables = [node] if node.name == "table" else node.find_all("table")
        for table in tables:
            cls = " ".join(table.get("class") or [])
            if "enemy-info-level" in cls or "wikitable" in cls:
                data = th_td_pairs(table)
                if data:
                    data = _clean_enemy_data(data)
                    data["特性"] = _parse_traits(table, data)
                    return data
    return {}


def parse_enemy(html):
    # type: (str) -> dict
    """解析敌人页 HTML，返回结构化敌人数据（dict，可直接 JSON 序列化）。"""
    soup = parse_html(html)
    enemy = {"name": "", "levels": []}
    for level in _section_id_to_level(soup):
        data = _parse_level(soup, level)
        if not data:
            continue
        if not enemy["name"]:
            enemy["name"] = data.get("名称", "")
        enemy["levels"].append({"level": level, "data": data})
    return enemy
