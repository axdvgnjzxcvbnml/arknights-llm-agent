"""知识图谱构建（NetworkX，只读构建脚本）。

从 PRTS 结构化语料（data/prts_raw）构建：
- 节点：operator:名字 / enemy:名字 / stage:编号 / skill:技能名
- 边（fact）：HAS_SKILL（干员-技能）、CONTAINS_ENEMY（关卡-敌人）
- 边（inferred，规则推断，非 PRTS 官方结论）：COUNTERS（干员-克制-敌人）、
  RECOMMENDS（关卡-推荐-干员）；规则与阈值集中见 configs/knowledge.yaml。

构建结果写入 data/graph/arknights_graph.graphml（gitignore），供
knowledge/graph/query_graph.py 只读查询与 api/server.py 图谱接口使用。
"""

import glob
import json
import os
import re
import sys

import networkx as nx
import yaml

__all__ = ["build_graph", "main"]

# 关卡敌情表里的"数量"列可能是 "12" 或 "1+3"（分批出怪）；本构建不展开波次，
# 直接按表内出现的敌人名称建边（一个敌人名一条 CONTAINS_ENEMY 边）。
COUNT_PATTERN = re.compile(r"^\d+(\+\d+)*$")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _stage_enemies(stage):
    """返回 [(显示名, count)]。敌人页可能缺 display（模板未解析出来时回退 name）。"""
    out = []
    for e in stage.get("enemies", []) or []:
        nm = e.get("display") or e.get("name")
        if not nm:
            continue
        cnt = str(e.get("count", ""))
        if cnt and not COUNT_PATTERN.match(cnt):
            cnt = ""
        out.append((nm, cnt))
    return out


def _skill_pairs(op):
    """返回 [(技能名, 类型)]；技能名缺失时跳过该技能。"""
    out = []
    for sk in op.get("skills", []) or []:
        nm = sk.get("name")
        if not nm:
            continue
        out.append((nm, sk.get("type", "")))
    return out


def _attr_num(v, default=0.0):
    """把属性值转成 float；无法解析（None/空/含范围）时返回 default，不误判。"""
    if v is None:
        return default
    s = str(v).strip().replace(",", "").replace("-", "")
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _enemy_attrs(level_row):
    return {
        "hp": _attr_num(level_row.get("HP")),
        "atk": _attr_num(level_row.get("攻击")),
        "defense": _attr_num(level_row.get("防御")),
        "resistance": _attr_num(level_row.get("法抗")),
        "speed": _attr_num(level_row.get("移动速度")),
    }


def _enemy_by_level(enemy):
    """敌人 stats -> {level: attrs}。缺 level 字段的用 -1 兜底。"""
    out = {}
    for s in enemy.get("stats", []) or []:
        lv = s.get("level")
        out[lv if lv is not None else -1] = _enemy_attrs(s)
    return out


def _high_defense_skill_keywords(op):
    """技能文本里出现的高防关键词（法伤/无视防御/固定伤害/真伤）命中集合。"""
    hits = set()
    for sk in op.get("skills", []) or []:
        text = "%s %s" % (sk.get("name", ""), sk.get("desc", ""))
        for kw in ("法术", "法伤", "无视防御", "固定伤害", "真实伤害"):
            if kw in text:
                hits.add(kw)
    return hits


def _operator_high_resistance_support(op):
    """干员在敌人高法抗侧的"硬信息"：减速/束缚/眩晕/沉默 等不依赖伤害类型的能力。"""
    support = set()
    text = "%s %s %s" % (op.get("trait", ""), op.get("desc", ""),
                          " ".join(sk.get("name", "") + sk.get("desc", "") for sk in
                                   op.get("skills", []) or []))
    for kw in ("减速", "束缚", "眩晕", "停顿", "沉默", "冰冻", "冻结", "脆弱"):
        if kw in text:
            support.add(kw)
    return support


def _star(op):
    try:
        return int(op.get("rarity", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _operator_class(op):
    return (op.get("class") or "").strip()


def _res_match(enemy, level_row):
    return _attr_num(level_row.get("法抗")) >= RULES["high_resistance_threshold"]


def _def_match(enemy, level_row):
    return _attr_num(level_row.get("防御")) >= RULES["high_defense_threshold"]


def _speed_match(enemy, level_row):
    return _attr_num(level_row.get("移动速度")) >= RULES["fast_speed_threshold"]


def _node_id(kind, name):
    return "%s:%s" % (kind, name)


def _enemy_display_to_page(enemies_dir, display):
    """敌情表显示名 -> 敌人 JSON 文件名（页面标题）。

    直接按显示名找不到时，用前缀匹配（敌情表可能写"变形者集群"而页面是
    "变形者集群(DC3)"）。返回文件名（无 .json）或 None。
    """
    if not display:
        return None
    cand = display
    while cand:
        p = os.path.join(enemies_dir, "%s.json" % cand)
        if os.path.isfile(p):
            return cand
        # 去掉末段（括号后缀/版本）再试：变形者集群(DC3) -> 变形者集群
        cand = re.sub(r"[\(（][^()（）]+[\)）]$", "", cand).strip()
    return None


def _operator_enemy_edge(rel, g, src, dst, data, add_counter):
    if g.has_edge(src, dst, rel):
        # 同 (干员,敌人) 多技能命中只记一次，计数并去重（稀疏化）
        e = g.edges[src, dst, rel]
        e["weight"] = int(e.get("weight", 0)) + 1
    else:
        add_counter()
        g.add_edge(src, dst, rel, weight=1, **data)


def _build_operator_enemy_edges(g, ops, enemies_by_page, ops_dir):
    """干员 -> 敌人 克制边（inferred）。"""
    def _add_counter():
        return None

    counters = 0

    def _count():
        return counters

    # 用局部计数变量（闭包内可变）
    _counters = {"n": 0}

    def _bump():
        _counters["n"] += 1

    for name, op in ops.items():
        cls = _operator_class(op)
        star = _star(op)
        keywords = _high_defense_skill_keywords(op)
        support = _operator_high_resistance_support(op)
        oid = _node_id("operator", name)
        for ename, enemy in enemies_by_page.items():
            for lv, attrs in enemy.items():
                basis = 0.0
                reasons = []
                if _def_match(enemy, lv) and (keywords or cls == "术师"):
                    basis = max(basis, 1.0 if cls == "术师" else 0.6)
                    reasons.append("high_defense")
                if _res_match(enemy, lv) and support:
                    basis = max(basis, 0.8)
                    reasons.append("high_resistance")
                if basis <= 0:
                    continue
                # 敌人按页面标题建 id（与 RAG 对齐），用 level 具体值去重
                eid = _node_id("enemy", ename)
                data = {"relation": "COUNTERS", "evidence": "inferred",
                        "basis": round(basis, 3),
                        "level": lv, "match": "|".join(reasons),
                        "skill_keywords": "|".join(sorted(keywords)),
                        "class": cls, "star": star}
                _operator_enemy_edge(g, "COUNTERS", oid, eid, data, _bump)
    # 边数写回
    return _counters["n"]


def _build_recommends(g, stages, ops):
    """关卡 -> 推荐干员（inferred）：对关内每个高防/高抗敌人，取克制它的干员集。"""
    # 先建 敌人 -> 干员 索引（与 COUNTERS 边一致，只读）
    enemy_to_ops = {}
    for u, v, data in g.edges(data=True):
        if data.get("relation") != "COUNTERS":
            continue
        enemy_to_ops.setdefault(v, []).append(u)
    rec = 0
    for sid, stage in stages.items():
        node_id = _node_id("stage", sid)
        if node_id not in g:
            continue
        seen = set()
        for ename, _cnt in _stage_enemies(stage):
            # 敌情表名字 -> 敌人节点
            page = _enemy_display_to_page("data/prts_raw/enemies", ename)
            eid = _node_id("enemy", page) if page else _node_id("enemy", ename)
            for oid in enemy_to_ops.get(eid, []):
                if oid in seen:
                    continue
                seen.add(oid)
                g.add_edge(node_id, oid, relation="RECOMMENDS", evidence="inferred",
                           support=1, score=0.0)
                rec += 1
    return rec


# 在模块加载后由 build_graph 填充的规则（读取 configs/knowledge.yaml）
RULES = {"high_defense_threshold": 800, "high_resistance_threshold": 50,
         "fast_speed_threshold": 2.0}


def build_graph(root="data/prts_raw", out="data/graph/arknights_graph.graphml",
                config_path=None):
    # type: (str, str, str) -> nx.MultiDiGraph
    """从 PRTS 结构化语料构建知识图谱（MultiDiGraph）。"""
    global RULES
    if config_path:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        rules = (cfg.get("graph") or {}).get("rules") or {}
        RULES.update({k: v for k, v in rules.items() if v is not None})

    g = nx.MultiDiGraph()
    ops_dir = os.path.join(root, "operators")
    enemies_dir = os.path.join(root, "enemies")
    stages_dir = os.path.join(root, "stages")

    # ---- 节点：干员 / 技能 / 敌人 / 关卡 ----
    ops = {}
    for p in sorted(glob.glob(os.path.join(ops_dir, "*.json"))):
        op = _load_json(p)
        name = op.get("name")
        if not name:
            continue
        ops[name] = op
        oid = _node_id("operator", name)
        g.add_node(oid, kind="operator", name=name, class=_operator_class(op),
                   star=_star(op))
        for sk_name, sk_type in _skill_pairs(op):
            sid = _node_id("skill", sk_name)
            if sid not in g:
                g.add_node(sid, kind="skill", name=sk_name, type=sk_type)
            g.add_edge(oid, sid, relation="HAS_SKILL", evidence="fact")

    enemies_by_page = {}
    for p in sorted(glob.glob(os.path.join(enemies_dir, "*.json"))):
        enemy = _load_json(p)
        page = os.path.splitext(os.path.basename(p))[0]
        name = enemy.get("name") or page
        eid = _node_id("enemy", page)
        g.add_node(eid, kind="enemy", name=name)
        enemies_by_page[page] = _enemy_by_level(enemy)

    for p in sorted(glob.glob(os.path.join(stages_dir, "*.json"))):
        stage = _load_json(p)
        code = stage.get("code")
        if not code:
            continue
        sid = _node_id("stage", str(code))
        g.add_node(sid, kind="stage", name=stage.get("name", ""),
                   title=stage.get("name", ""))
        for ename, cnt in _stage_enemies(stage):
            page = _enemy_display_to_page(enemies_dir, ename)
            eid = _node_id("enemy", page if page else ename)
            if eid not in g:
                # 敌情表引用未爬到的敌人：建占位节点（kind=enemy，无 stats）
                g.add_node(eid, kind="enemy", name=ename, placeholder=True)
            g.add_edge(sid, eid, relation="CONTAINS_ENEMY", evidence="fact",
                       count=cnt)

    # ---- inferred 边：克制 / 推荐 ----
    counters = _build_operator_enemy_edges(g, ops, enemies_by_page, ops_dir)
    recommends = _build_recommends(g, stages, ops)

    out_dir = os.path.dirname(os.path.abspath(out))
    os.makedirs(out_dir, exist_ok=True)
    nx.write_graphml(g, out)
    return g


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="构建 PRTS 知识图谱（NetworkX）")
    ap.add_argument("--root", default="data/prts_raw")
    ap.add_argument("--out", default="data/graph/arknights_graph.graphml")
    ap.add_argument("--config", default="configs/knowledge.yaml")
    args = ap.parse_args(argv)
    g = build_graph(root=args.root, out=args.out, config_path=args.config)
    stats = g.graph
    print("图谱构建完成：%d 节点 / %d 边 -> %s" % (g.number_of_nodes(), g.number_of_edges(), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
