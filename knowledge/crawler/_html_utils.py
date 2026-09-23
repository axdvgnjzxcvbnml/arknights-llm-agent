"""PRTS Wiki HTML 解析共享工具（内部模块）。

基于真实页面结构探查（2026-09 验证于 阿米娅 / 源石虫 / 3-8 三个页面）：

- 章节标题：<div class="mw-heading mw-heading2"><h2 id="章节名">...</h2></div>
  章节内容 = heading 所在 div 的后续兄弟节点（直到下一个 mw-heading）。
- 表格：<table class="wikitable ...">。
- 干员元数据：页面内嵌 <script> 中的 var char_info = {...} JS 对象。
"""

import json
import re

from bs4 import BeautifulSoup

__all__ = [
    "parse_html",
    "get_section",
    "iter_section_tables",
    "table_rows",
    "th_td_pairs",
    "extract_js_object",
]


def parse_html(html):
    # type: (str) -> BeautifulSoup
    """把整页 HTML 解析为 BeautifulSoup 对象。"""
    return BeautifulSoup(html, "lxml")


def get_section(soup, section_id):
    # type: (BeautifulSoup, str) -> list
    """返回指定章节（h2 id）下的所有兄弟节点列表（不含标题行）。"""
    h2 = soup.find("h2", id=section_id)
    if h2 is None:
        return []
    nodes = []
    for node in h2.parent.find_next_siblings():
        if node.name == "div" and "mw-heading" in (node.get("class") or []):
            break
        nodes.append(node)
    return nodes


def iter_section_tables(soup, section_id):
    # type: (BeautifulSoup, str) -> iter
    """遍历章节内的所有 <table>，按出现顺序 yield（含节点本身是 table 的情况）。"""
    for node in get_section(soup, section_id):
        if node.name == "table":
            yield node
        else:
            for table in node.find_all("table"):
                yield table


def table_rows(table, keep_empty=False):
    # type: (BeautifulSoup, bool) -> list
    """把表格转成行列表，每行为 cell 文本列表（按 th/td 出现顺序）。"""
    rows = []
    for tr in table.find_all("tr"):
        cells = []
        for c in tr.find_all(["th", "td"]):
            text = re.sub(r"\s+", " ", c.get_text(" ", strip=True))
            cells.append(text)
        if keep_empty or any(cells):
            rows.append(cells)
    return rows


def th_td_pairs(table):
    # type: (BeautifulSoup) -> dict
    """从表格提取"字段名 -> 值"字典（PRTS 属性表通用启发式）。

    规则（基于 enemy-info-level / char-base-attr-table 等实测结构）：
    - 行内同时有 th 与 td：按顺序逐对配对（如 生命自回速度 -> 0）；
    - 行内只有 th：记为待配对字段名；
    - 行内只有 td：与待配对字段名按顺序配对。
    - 特例：行内 th 含"名称"且 th 多于 td（如碎骨等 boss 页，名称/地位的
      值在下一行），此时 th 全部挂起等待下一行 td 配对。
    """
    pairs = {}
    pending = []  # type: list
    for tr in table.find_all("tr"):
        ths = [re.sub(r"\s+", " ", t.get_text(" ", strip=True)) for t in tr.find_all("th")]
        tds = [re.sub(r"\s+", " ", t.get_text(" ", strip=True)) for t in tr.find_all("td")]
        if ths and tds:
            if "名称" in ths and len(ths) > len(tds):
                pending = list(ths)
            else:
                for k, v in zip(ths, tds):
                    if k:
                        pairs[k] = v
        elif tds and pending:
            for k, v in zip(pending, tds):
                if k:
                    pairs[k] = v
            pending = []
        elif ths:
            pending = list(ths)
    return pairs


def _strip_trailing_commas(text):
    """删除字符串字面量之外的尾随逗号（JS 对象允许 ,} / ,] ，JSON 不允许）。

    逗号后允许出现空白/换行（PRTS 页面存在 ",\n            }" 多行格式）。
    """
    out = []
    in_str = False
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if in_str:
            # JS 字符串内 \' 是合法转义但 JSON 非法，转为普通单引号
            if ch == "\\" and i + 1 < n and text[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            out.append(ch)
            if ch == '"':
                in_str = False
            i += 1
        elif ch == '"':
            in_str = True
            out.append(ch)
            i += 1
        elif ch == ",":
            # 向后跳过空白，若紧跟 } 或 ] 则判定为尾随逗号并丢弃
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
            else:
                out.append(ch)
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def extract_js_object(text, var_name):
    # type: (str, str) -> dict
    """从 <script> 文本中提取 var <var_name> = {...}; 并解析为 dict。

    注意：PRTS 页面格式为 var char_info={...}（等号两侧可能无空格），
    且 JS 对象允许尾随逗号，解析前先清洗。
    """
    pat = re.compile(r"var\s+%s\s*=\s*\{" % re.escape(var_name))
    m = pat.search(text)
    if not m:
        return {}
    brace = m.end() - 1  # '{' 的位置
    depth = 0
    in_str = False
    esc = False
    for j in range(brace, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(_strip_trailing_commas(text[brace : j + 1]))
                    except ValueError:
                        return {}
    return {}
