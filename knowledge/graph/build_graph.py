"""从 data/prts_raw/ 的 JSON 构建明日方舟知识图谱（NetworkX）。

节点（4 类）：
- operator  干员（职业/分支/星级/标签/费用/伤害类型信号）
- skill     技能（归属干员）
- enemy     敌人（取最强级别的 防御/法抗/速度/地位/特性；关卡敌情表独有敌人也建节点）
- stage     关卡（code/名称）

边（4 类，relation 属性区分；evidence 分级）：
- operator -[HAS_SKILL]->     skill   evidence=fact     （干员页技能表，结构化）
- stage    -[CONTAINS_ENEMY]-> enemy  evidence=fact     （关卡敌情表，结构化，带数量/级别）
- operator -[COUNTERS]->      enemy   evidence=inferred （规则推导，附 rule 与匹配数值）
- stage    -[RECOMMENDS]->    operator evidence=inferred（关卡敌人 -> 克制规则聚合）

克制规则（集中在 derive_counter_rules，阈值在 configs/knowledge.yaml）：
- R1 high_defense_to_arts：敌人防御>=阈值（重装型）
      -> 术师（法术伤害无视防御）或技能描述含"法术伤害/无视防御/真实伤害"的干员
- R2 high_resistance_to_physical：敌人法抗>=阈值（高抗型）
      -> 狙击/近卫（物理输出职业）
- R3 fast_enemy_to_control：敌人移速>=阈值或描述含"高速"
      -> 技能描述含"减速/束缚/眩晕/停顿/冻结"的干员

输出：GraphML 到 data/graph/arknights_graph.graphml + build_stats.json。
# TODO-V100: 无 GPU 依赖（纯规则+NetworkX）；后续可在 V100 上用 LLM 从攻略文本抽取更精细边。
"""

import argparse
import glob
import json
import os
import re

import networkx as nx

from ..rag.config import DEFAULT_CONFIG_PATH, load_knowledge_config

__all__ = ["build_graph", "derive_counter_rules"]


def _stage_title(stem, data):
    # type: (str, dict) -> str
    """关卡标题还原：样本期文件名可能是"3-8"（缺名称），用 code+name 还原"3-8 黄昏"。"""
    if " " in stem:
        return stem
    code = data.get("code") or stem
    name = data.get("normal", {}).get("name", "")
    return ("%s %s" % (code, name)).strip() if name else stem

REL_HAS_SKILL = "HAS_SKILL"
REL_CONTAINS = "CONTAINS_ENEMY"
REL_COUNTERS = "COUNTERS"
REL_RECOMMENDS = "RECOMMENDS"

_ARTS_KEYWORDS = ("法术伤害", "无视防御", "真实伤害")
_PHYSICAL_CLASSES = ("狙击", "近卫")
_CONTROL_KEYWORDS = ("减速", "束缚", "眩晕", "停顿", "冻结")


def _to_float(value):
    # type: (object) -> float
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _operator_signals(op):
    # type: (dict) -> dict
    """从干员 JSON 提取克制规则所需信号。"""
    meta = op.get("meta", {}) or {}
    skill_text = []
    for s in op.get("skills", []) or []:
        skill_text.append(s.get("type", "") or "")
        for lv in s.get("levels", []) or []:
            if lv.get("desc"):
                skill_text.append(lv["desc"])
    blob = " ".join(skill_text)
    return {
        "name": meta.get("name") or op.get("name", ""),
        "class": meta.get("class", ""),
        "branch": meta.get("branch", ""),
        "star": meta.get("star_rating"),
        "tags": meta.get("tag", ""),
        "is_caster": meta.get("class") == "术师",
        "is_physical_dps": meta.get("class") in _PHYSICAL_CLASSES,
        "has_arts_or_true": any(k in blob for k in _ARTS_KEYWORDS),
        "has_control": any(k in blob for k in _CONTROL_KEYWORDS),
        "skill_text": blob,
    }


def _enemy_record_from_json(data):
    # type: (dict) -> dict
    """取敌人最强级别（levels 末项）的属性作为代表值。"""
    levels = data.get("levels", []) or []
    if not levels:
        return {}
    top = levels[-1].get("data", {}) or {}
    traits = top.get("特性") or []
    if isinstance(traits, (list, tuple)):
        traits = "、".join(str(t) for t in traits if t)
    return {
        "name": data.get("name") or top.get("名称", ""),
        "defense": _to_float(top.get("防御力")),
        "resistance": _to_float(top.get("法术抗性")),
        "speed": _to_float(top.get("移动速度")),
        "hp": _to_float(top.get("最大生命值")),
        "position": top.get("地位", ""),
        "traits": traits or "",
        "desc": top.get("描述", ""),
        "from_stage_table": False,
    }


def _enemy_record_from_stage_row(row):
    # type: (dict) -> dict
    """关卡敌情表中的敌人（可能没有独立敌人 JSON），用表格数值建轻量记录。"""
    return {
        "name": row.get("名称", ""),
        "defense": _to_float(row.get("防御力")),
        "resistance": _to_float(row.get("法术抗性")),
        "speed": _to_float(row.get("移动速度")),
        "hp": _to_float(row.get("生命值")),
        "position": row.get("地位", ""),
        "traits": "",
        "desc": "",
        "from_stage_table": True,
    }


def derive_counter_rules(enemy, rules_cfg):
    # type: (dict, dict) -> list
    """对单个敌人返回命中的克制规则列表。

    每条为 (rule_id, reason, matchers)；matchers 按优先级排列：
        (signal 字段, match_basis, weight)
    - class（职业级核心克制，weight=1.0）：如术师克重甲、物理职业克高抗
    - skill_keyword（技能机制克制，weight=0.6）：泛用性低于本职克制
    干员命中靠前的 matcher 即决定该边 basis/weight，避免完全二分导致排名无区分度。
    """
    hits = []
    defense_t = float(rules_cfg.get("high_defense_threshold", 800))
    res_t = float(rules_cfg.get("high_resistance_threshold", 50))
    speed_t = float(rules_cfg.get("fast_speed_threshold", 2.0))

    if enemy.get("defense") is not None and enemy["defense"] >= defense_t:
        hits.append((
            "R1_high_defense_to_arts",
            "敌人防御力%s>=%s（重装型），需法术伤害/无视防御/真实伤害"
            % (enemy["defense"], defense_t),
            [("is_caster", "class", 1.0), ("has_arts_or_true", "skill_keyword", 0.6)],
        ))
    if enemy.get("resistance") is not None and enemy["resistance"] >= res_t:
        hits.append((
            "R2_high_resistance_to_physical",
            "敌人法术抗性%s>=%s（高抗型），物理输出职业更优"
            % (enemy["resistance"], res_t),
            [("is_physical_dps", "class", 1.0)],
        ))
    fast = (enemy.get("speed") is not None and enemy["speed"] >= speed_t) or \
           ("高速" in (enemy.get("desc") or "") + (enemy.get("traits") or ""))
    if fast:
        hits.append((
            "R3_fast_enemy_to_control",
            "敌人移速%s（或描述含高速），需要减速/束缚/眩晕等控制"
            % enemy.get("speed"),
            [("has_control", "skill_keyword", 0.6)],
        ))
    return hits


def _operator_match(signal, matchers):
    # type: (dict, list) -> tuple
    """返回命中的 (basis, weight)，无命中返回 None。"""
    for field, basis, weight in matchers:
        if signal.get(field):
            return basis, weight
    return None


def _add_edge(g, src, dst, relation, evidence, **attrs):
    # type: (nx.MultiDiGraph, str, str, str, str) -> None
    """MultiDiGraph 同对节点可有多条边（不同 rule），按 relation+rule 去重。"""
    key = attrs.get("rule", relation)
    if g.has_edge(src, dst, key=key):
        return
    attrs.update({"relation": relation, "evidence": evidence, "rule": attrs.get("rule", relation)})
    g.add_edge(src, dst, key=key, **attrs)


def build_graph(config):
    # type: (dict) -> dict
    gcfg = config["graph"]
    rag_raw = config["rag"]["build"]["raw_dir"]
    rules_cfg = gcfg.get("rules", {})

    operators = [(os.path.splitext(os.path.basename(p))[0], json.load(open(p, encoding="utf-8")))
                 for p in sorted(glob.glob(os.path.join(rag_raw, "operators", "*.json")))]
    enemies = [(os.path.splitext(os.path.basename(p))[0], json.load(open(p, encoding="utf-8")))
               for p in sorted(glob.glob(os.path.join(rag_raw, "enemies", "*.json")))]
    stages = [(os.path.splitext(os.path.basename(p))[0], json.load(open(p, encoding="utf-8")))
              for p in sorted(glob.glob(os.path.join(rag_raw, "stages", "*.json")))]
    print("[graph] JSON：干员 %d，敌人 %d，关卡 %d" % (len(operators), len(enemies), len(stages)))

    g = nx.MultiDiGraph()

    # ---- 干员 + 技能（fact）；实体身份统一用页面标题（文件名） ----
    # 与敌人节点口径一致：防止异格页面（如"阿米娅(近卫)"）的 meta.name 缺后缀时
    # 被错误合并为同一节点。sig["name"]（meta.name）仅作显示用信号，不作身份。
    signals = {}
    for page, op in operators:
        sig = _operator_signals(op)
        name = page
        if not name:
            continue
        signals[name] = sig
        g.add_node("operator:%s" % name,
                   kind="operator", name=name, display_name=sig.get("name") or name,
                   page_title=page, **{
                       k: ("" if sig.get(k) is None else sig.get(k))
                       for k in ("class", "branch", "tags")
                   },
                   star=sig.get("star") if sig.get("star") is not None else -1)
        for skill in op.get("skills", []) or []:
            sname = skill.get("name")
            if not sname:
                continue
            sid = "skill:%s:%s" % (name, sname)
            g.add_node(sid, kind="skill", name=sname, owner=name,
                       skill_type=skill.get("type", ""))
            _add_edge(g, "operator:%s" % name, sid, REL_HAS_SKILL, "fact")

    # ---- 敌人：页面标题作为实体身份，显示名（名称）单独建索引 ----
    # 消歧义形态（"X(DC3)"与"X"）是两个节点；关卡表按显示名引用，需 display->page 映射。
    enemy_records = {}
    display_to_pages = {}
    for page, data in enemies:
        rec = _enemy_record_from_json(data)
        if not rec.get("name"):
            rec["name"] = page
        rec["page"] = page
        enemy_records[page] = rec
        display_to_pages.setdefault(rec["name"], []).append(page)

    def resolve_enemy(display_name):
        # type: (str) -> str
        """关卡表显示名 -> 敌人页面身份；多形态时优先无消歧义后缀的基础形态。"""
        pages = display_to_pages.get(display_name, [])
        if not pages:
            return display_name  # 纯关卡表敌人：身份即显示名
        if display_name in pages:
            return display_name
        return sorted(pages, key=len)[0]

    stage_rows = {}  # 敌人页面身份 -> [(code, row)]
    for page, data in stages:
        title = _stage_title(page, data)
        code = data.get("code", title.split(" ")[0])
        g.add_node("stage:%s" % code, kind="stage", code=code,
                   name=data.get("normal", {}).get("name", ""), title=title)
        for row in data.get("enemies", []) or []:
            display = row.get("名称")
            if not display:
                continue
            epage = resolve_enemy(display)
            stage_rows.setdefault(epage, []).append((code, row))
            if epage not in enemy_records:
                rec = _enemy_record_from_stage_row(row)
                rec["page"] = epage
                enemy_records[epage] = rec
    for epage, rec in enemy_records.items():
        g.add_node("enemy:%s" % epage, kind="enemy", name=rec.get("name", epage),
                   page_title=epage,
                   defense=rec["defense"] if rec["defense"] is not None else -1.0,
                   resistance=rec["resistance"] if rec["resistance"] is not None else -1.0,
                   speed=rec["speed"] if rec["speed"] is not None else -1.0,
                   position=rec.get("position", ""), traits=rec.get("traits", ""),
                   source="enemy_json" if not rec["from_stage_table"] else "stage_table")

    # ---- 关卡-包含-敌人（fact，带数量/级别） ----
    for epage, occ in stage_rows.items():
        for code, row in occ:
            _add_edge(g, "stage:%s" % code, "enemy:%s" % epage,
                      REL_CONTAINS, "fact",
                      count=str(row.get("数量", "")), level=str(row.get("级别", "")))

    # ---- 干员-克制-敌人（inferred，带 basis/weight） ----
    counter_edges = 0
    enemy_rules = {}  # ename -> [(rule_id, reason, matchers)]
    for ename, rec in enemy_records.items():
        enemy_rules[ename] = derive_counter_rules(rec, rules_cfg)
    for ename, rule_hits in enemy_rules.items():
        for rule_id, reason, matchers in rule_hits:
            for name, sig in signals.items():
                match = _operator_match(sig, matchers)
                if match:
                    basis, weight = match
                    _add_edge(g, "operator:%s" % name, "enemy:%s" % ename,
                              REL_COUNTERS, "inferred", rule=rule_id, reason=reason,
                              match_basis=basis, weight=float(weight))
                    counter_edges += 1

    # ---- 关卡-推荐-干员（inferred：关卡敌人 -> 克制规则聚合，加权打分） ----
    recommend_edges = 0
    for page, data in stages:
        title = _stage_title(page, data)
        code = data.get("code", title.split(" ")[0])
        # name -> {rules, enemies, best: {enemy: best_weight}}
        votes = {}
        for row in data.get("enemies", []) or []:
            ename = resolve_enemy(row.get("名称", ""))
            for rule_id, reason, matchers in enemy_rules.get(ename, []):
                for name, sig in signals.items():
                    match = _operator_match(sig, matchers)
                    if not match:
                        continue
                    _, weight = match
                    v = votes.setdefault(name, {"rules": set(), "enemies": set(),
                                                "best": {}})
                    v["rules"].add(rule_id)
                    v["enemies"].add(ename)
                    # 同一敌人多条规则命中时取最高权重
                    v["best"][ename] = max(v["best"].get(ename, 0.0), weight)
        for name, v in votes.items():
            score = round(sum(v["best"].values()), 2)
            _add_edge(g, "stage:%s" % code, "operator:%s" % name,
                      REL_RECOMMENDS, "inferred",
                      rule="aggregated_counter",
                      matched_enemies="、".join(sorted(v["enemies"])),
                      matched_rules="、".join(sorted(v["rules"])),
                      support=len(v["enemies"]), score=score)
            recommend_edges += 1

    # ---- 落盘 ----
    out_dir = gcfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    graphml_path = os.path.join(out_dir, gcfg.get("graphml_file", "arknights_graph.graphml"))
    # GraphML 不支持 None，写出前统一转空串（数值缺失统一用 -1，已在建点时处理）
    nx.write_graphml(g, graphml_path, encoding="utf-8")

    def _count(rel):
        return sum(1 for _, _, d in g.edges(data=True) if d.get("relation") == rel)

    stats = {
        "nodes": {
            "total": g.number_of_nodes(),
            "operator": len(signals),
            "skill": sum(1 for _, d in g.nodes(data=True) if d.get("kind") == "skill"),
            "enemy": len(enemy_records),
            "stage": len(stages),
        },
        "edges": {
            "total": g.number_of_edges(),
            "HAS_SKILL": _count(REL_HAS_SKILL),
            "CONTAINS_ENEMY": _count(REL_CONTAINS),
            "COUNTERS": _count(REL_COUNTERS),
            "RECOMMENDS": _count(REL_RECOMMENDS),
        },
        "graphml": graphml_path,
    }
    with open(os.path.join(out_dir, "build_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("[graph] 完成：%s" % json.dumps(stats, ensure_ascii=False))
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建知识图谱")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)
    build_graph(load_knowledge_config(args.config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
