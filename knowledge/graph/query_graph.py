"""知识图谱查询接口（GraphML 只读加载）。

支持查询：
- skills_of_operator(name)         干员拥有的技能
- enemies_in_stage(code)           关卡包含的敌人（带数量/级别）
- operators_countering(name)       克制某敌人的干员（附规则与原因）
- enemies_countered_by(name)       某干员能克制哪些敌人
- operators_for_stage(code)        关卡推荐干员（按支持度排序）
- counter_heavy_armor(threshold)   "克制重装敌人的干员有哪些"：高防敌人 -> 克制干员
- stats()                          图谱规模统计

CLI:
    python -m knowledge.graph.query_graph demo
    python -m knowledge.graph.query_graph counter-enemy 碎骨
    python -m knowledge.graph.query_graph stage-ops 3-8
    python -m knowledge.graph.query_graph heavy-armor
"""

import argparse
import os

import networkx as nx

from ..rag.config import DEFAULT_CONFIG_PATH, load_knowledge_config

__all__ = ["GraphQuery"]


class GraphQuery(object):
    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        # type: (dict, str) -> None
        self.config = config or load_knowledge_config(config_path)
        path = os.path.join(self.config["graph"]["output_dir"],
                            self.config["graph"].get("graphml_file", "arknights_graph.graphml"))
        if not os.path.exists(path):
            raise FileNotFoundError("图谱不存在: %s，请先运行 python -m knowledge.graph.build_graph" % path)
        self.graph = nx.read_graphml(path)
        self._heavy_armor_cache = {}  # threshold -> 已排序完整结果（全量语料下惰性预计算一次）

    def _out(self, node_id, relation):
        # type: (str, str) -> list
        rows = []
        for _, dst, data in self.graph.out_edges(node_id, data=True):
            if data.get("relation") == relation:
                rows.append((dst, data))
        return rows

    def skills_of_operator(self, name):
        # type: (str) -> list
        out = []
        for sid, data in self._out("operator:%s" % name, "HAS_SKILL"):
            node = self.graph.nodes[sid]
            out.append({"skill": node.get("name"), "skill_type": node.get("skill_type", "")})
        return out

    def enemies_in_stage(self, code):
        # type: (str) -> list
        out = []
        for eid, data in self._out("stage:%s" % code, "CONTAINS_ENEMY"):
            node = self.graph.nodes[eid]
            out.append({
                "enemy": node.get("name"),
                "count": data.get("count", ""),
                "level": data.get("level", ""),
                "position": node.get("position", ""),
                "defense": node.get("defense", -1),
                "resistance": node.get("resistance", -1),
            })
        return out

    def _resolve_enemy(self, name):
        # type: (str) -> str
        """敌人输入名 -> 节点 ID。节点 ID 用页面标题，消歧义形态按显示名回退匹配。"""
        exact = "enemy:%s" % name
        if exact in self.graph:
            return exact
        for nid, node in self.graph.nodes(data=True):
            if node.get("kind") == "enemy" and node.get("name") == name:
                return nid
        return exact

    def operators_countering(self, enemy_name):
        # type: (str) -> list
        # COUNTERS 边方向为 operator -> enemy，反查入边
        out = []
        for src, _, data in self.graph.in_edges(self._resolve_enemy(enemy_name), data=True):
            if data.get("relation") != "COUNTERS":
                continue
            node = self.graph.nodes[src]
            out.append({
                "operator": node.get("name"),
                "class": node.get("class", ""),
                "star": node.get("star", -1),
                "rule": data.get("rule"),
                "evidence": data.get("evidence"),
                "match_basis": data.get("match_basis", ""),
                "weight": data.get("weight", 0.0),
                "reason": data.get("reason", ""),
            })
        return out

    def enemies_countered_by(self, operator_name):
        # type: (str) -> list
        out = []
        for eid, data in self._out("operator:%s" % operator_name, "COUNTERS"):
            node = self.graph.nodes[eid]
            out.append({
                "enemy": node.get("name"),
                "defense": node.get("defense", -1),
                "resistance": node.get("resistance", -1),
                "rule": data.get("rule"),
                "match_basis": data.get("match_basis", ""),
                "weight": data.get("weight", 0.0),
                "reason": data.get("reason", ""),
            })
        return out

    def operators_for_stage(self, code):
        # type: (str) -> list
        out = []
        for oid, data in self._out("stage:%s" % code, "RECOMMENDS"):
            node = self.graph.nodes[oid]
            out.append({
                "operator": node.get("name"),
                "class": node.get("class", ""),
                "star": node.get("star", -1),
                "support": data.get("support", 0),
                "score": data.get("score", 0.0),
                "matched_enemies": data.get("matched_enemies", ""),
                "matched_rules": data.get("matched_rules", ""),
            })
        # 加权分降序，同分按星级降序（高星练度优先级高）
        out.sort(key=lambda x: (-x["score"], -x["star"]))
        return out

    def counter_heavy_armor(self, threshold=None, limit=20):
        # type: (float, int) -> list
        """高防（重装型）敌人 -> 克制它们的干员。

        全量语料下高防敌人很多（防>=阈值约占 1/5），职业级 COUNTERS 推断边天然偏密，
        逐个敌人反查会退化为 O(E·N)。这里对 COUNTERS 边做**单次遍历**聚票，按
        加权支持度（覆盖多少高防敌人、职业/技能权重）排序，并默认只回 top-N，保证：
        1) 响应快（一次边遍历，非嵌套查询）；2) 结果有区分度（不是返回全部术师）。
        evidence 恒为 inferred，调用方不得当事实。limit=None 返回全部。
        """
        if threshold is None:
            threshold = float(self.config["graph"]["rules"]["high_defense_threshold"])
        if threshold in self._heavy_armor_cache:
            ranked = self._heavy_armor_cache[threshold]
            return ranked if limit is None else ranked[:limit]
        # 高防敌人节点集合（节点 id -> 显示名）
        heavy = {}
        for nid, node in self.graph.nodes(data=True):
            if node.get("kind") != "enemy":
                continue
            dfn = node.get("defense")
            if dfn is None:
                continue
            try:
                if float(dfn) >= threshold:
                    heavy[nid] = node.get("name")
            except (TypeError, ValueError):
                continue
        votes = {}
        # 只遍历高防敌人集合的入边（COUNTERS 方向 operator->enemy），避免扫全图 20+ 万边
        for src, dst, data in self.graph.in_edges(list(heavy.keys()), data=True):
            if data.get("relation") != "COUNTERS":
                continue
            node = self.graph.nodes[src]
            op = node.get("name")
            v = votes.setdefault(op, {"class": node.get("class", ""),
                                     "star": int(node.get("star", -1) or -1),
                                     "enemies": set(), "score": 0.0})
            v["enemies"].add(heavy[dst])
            try:
                v["score"] += float(data.get("weight", 0.0) or 0.0)
            except (TypeError, ValueError):
                pass
        out = []
        for op, v in votes.items():
            out.append({"operator": op, "class": v["class"], "star": v["star"],
                        "heavy_enemies": sorted(v["enemies"]),
                        "count": len(v["enemies"]),
                        "score": round(v["score"], 2)})
        out.sort(key=lambda x: (-x["score"], -x["star"], x["operator"]))
        self._heavy_armor_cache[threshold] = out  # 首次计算后缓存，后续查询 <1ms
        return out if limit is None else out[:limit]

    def stats(self):
        # type: () -> dict
        kinds = {}
        for _, d in self.graph.nodes(data=True):
            kinds[d.get("kind")] = kinds.get(d.get("kind"), 0) + 1
        rels = {}
        for _, _, d in self.graph.edges(data=True):
            rels[d.get("relation")] = rels.get(d.get("relation"), 0) + 1
        return {"nodes": kinds, "edges": rels}


def _print_demo(gq):
    # type: (GraphQuery) -> None
    print("== 图谱规模 ==")
    print(gq.stats())
    print("\n== 干员-拥有-技能：能天使 ==")
    for s in gq.skills_of_operator("能天使"):
        print("  ", s)
    print("\n== 关卡-包含-敌人：3-8 ==")
    for e in gq.enemies_in_stage("3-8"):
        print("  ", e)
    print("\n== 干员-克制-敌人：碎骨（数值检验型 boss，预期无类型弱点） ==")
    counters = gq.operators_countering("碎骨")
    if not counters:
        print("   无克制边（碎骨防/抗未达阈值，规则上不具备类型弱点，符合预期）")
    for op in counters:
        print("  ", op["operator"], op["class"], op["rule"], "|", op["reason"])
    print("\n== 关卡-推荐-干员：10-17 坚城高墙（加权分 Top10） ==")
    for op in gq.operators_for_stage("10-17")[:10]:
        print("  %s(%s,%s星) score=%s support=%d <- %s" %
              (op["operator"], op["class"], op["star"], op["score"],
               op["support"], op["matched_enemies"]))
    print("\n== 克制重装敌人的干员（防御>=阈值）Top10（职业克制权重1.0优先） ==")
    for op in gq.counter_heavy_armor()[:10]:
        print("  %s(%s,%s星) score=%s 命中%d个: %s" %
              (op["operator"], op["class"], op["star"], op["score"], op["count"],
               "、".join(op["heavy_enemies"][:4])))


def main(argv=None):
    parser = argparse.ArgumentParser(description="知识图谱查询")
    parser.add_argument("command", choices=["demo", "counter-enemy", "stage-ops",
                                            "operator-skills", "stage-enemies", "heavy-armor"])
    parser.add_argument("arg", nargs="?", default="")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)
    gq = GraphQuery(config=load_knowledge_config(args.config))
    if args.command == "demo":
        _print_demo(gq)
    elif args.command == "counter-enemy":
        for op in gq.operators_countering(args.arg):
            print("%s\t%s\t%s\t%s" % (op["operator"], op["class"], op["rule"], op["reason"]))
    elif args.command == "stage-ops":
        for op in gq.operators_for_stage(args.arg):
            print("%s\t%s\t%s\t%s" % (op["operator"], op["class"], op["support"],
                                      op["matched_enemies"]))
    elif args.command == "operator-skills":
        for s in gq.skills_of_operator(args.arg):
            print("%s\t%s" % (s["skill"], s["skill_type"]))
    elif args.command == "stage-enemies":
        for e in gq.enemies_in_stage(args.arg):
            print("%s\t%s\t%s" % (e["enemy"], e["count"], e["level"]))
    elif args.command == "heavy-armor":
        for op in gq.counter_heavy_armor():
            print("%s\t%s\t%s" % (op["operator"], op["class"], "、".join(op["heavy_enemies"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
