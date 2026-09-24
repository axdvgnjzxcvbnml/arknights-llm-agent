"""知识图谱只读查询（NetworkX）。

加载 data/graph/arknights_graph.graphml（约 83M，首查约 9s）并提供：
- stats()：节点/边按类型统计；
- neighbors(node_id)：节点的出边/入边邻居（带 relation/evidence）；
- stage_enemies(stage_id)：关卡敌情（CONTAINS_ENEMY 边）；
- recommend_for_stage(stage_id, ...)：按敌情与克制边做推荐（inferred）。

设计约束：
- 只读：本模块不修改图；图谱由 knowledge/graph/build_graph.py 构建。
- 懒加载：import 本模块不读盘；首次调用方法才加载 graphml。
- 节点 id 形如 operator:能天使 / enemy:碎骨 / stage:3-8 / skill:过载模式。
- evidence 语义：HAS_SKILL / CONTAINS_ENEMY = fact（PRTS 结构化事实）；
  COUNTERS / RECOMMENDS = inferred（规则推断，非官方结论）。
"""

import glob
import os

import networkx as nx

__all__ = ["GraphQuery", "GraphMissingError"]

_DEFAULT_GRAPHML = os.path.join("data", "graph", "arknights_graph.graphml")


class GraphMissingError(FileNotFoundError):
    """图谱文件缺失（尚未构建）。"""


def _find_graphml(root):
    hits = glob.glob(os.path.join(root, "*.graphml"))
    return hits[0] if hits else None


class GraphQuery(object):
    """知识图谱只读查询入口。构造/首查才加载 graphml（约 83M，约 9s）。"""

    def __init__(self, config_path=None, graphml=None):
        # type: (str, str) -> None
        self._graphml = graphml or _DEFAULT_GRAPHML
        self._g = None
        if config_path:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            gcfg = cfg.get("graph") or {}
            out_dir = gcfg.get("output_dir", "data/graph")
            self._graphml = os.path.join(out_dir, gcfg.get("graphml_file", "arknights_graph.graphml"))

    @property
    def graph(self):
        # type: () -> nx.MultiDiGraph
        if self._g is None:
            if not os.path.isfile(self._graphml):
                raise GraphMissingError("图谱文件不存在：%s（先运行 scripts/build_graph.sh）"
                                        % self._graphml)
            self._g = nx.read_graphml(self._graphml)
        return self._g

    def stats(self):
        # type: () -> dict
        g = self.graph
        nodes = {}
        edges = {}
        for _, d in g.nodes(data=True):
            k = d.get("kind", "?")
            nodes[k] = nodes.get(k, 0) + 1
        for _, _, d in g.edges(data=True):
            r = d.get("relation", "?")
            edges[r] = edges.get(r, 0) + 1
        return {"nodes": nodes, "edges": edges}

    def neighbors(self, node_id):
        # type: (str) -> list
        """返回 (relation, neighbor_id, direction, data) 列表，direction ∈ out/in。"""
        g = self.graph
        out = []
        if node_id not in g:
            return out
        for _, dst, data in g.out_edges(node_id, data=True):
            out.append((data.get("relation", ""), dst, "out", data))
        for src, _, data in g.in_edges(node_id, data=True):
            out.append((data.get("relation", ""), src, "in", data))
        return out

    def stage_enemies(self, stage_id):
        # type: (str) -> list
        """关卡敌情：返回 [(enemy_id, count)]，顺序按图谱边序。"""
        g = self.graph
        sid = "stage:%s" % stage_id
        if sid not in g:
            return []
        out = []
        for _, dst, data in g.out_edges(sid, data=True):
            if data.get("relation") == "CONTAINS_ENEMY":
                out.append((dst, data.get("count", "")))
        return out

    def recommend_for_stage(self, stage_id, top_n=20, min_support=1):
        # type: (str, int, int) -> list
        """按关卡敌情推荐干员（inferred）。

        收集本关所有敌人的 COUNTERS 干员，按支持度（命中敌人数）降序取 top_n；
        结果每项：{operator, star, class, support, matched_enemies, evidence:inferred}。
        """
        g = self.graph
        sid = "stage:%s" % stage_id
        if sid not in g:
            return []
        enemies = [eid for eid, _cnt in self.stage_enemies(stage_id)]
        if not enemies:
            return []
        score = {}
        matched = {}
        for eid in enemies:
            for src, _, data in g.in_edges(eid, data=True):
                if data.get("relation") != "COUNTERS":
                    continue
                if src not in score:
                    d = g.nodes[src]
                    score[src] = {"operator": d.get("name", src), "star": d.get("star", 0),
                                  "class": d.get("class", ""), "support": 0,
                                  "matched_enemies": [], "evidence": "inferred"}
                score[src]["support"] += 1
                matched.setdefault(src, []).append(eid.split(":", 1)[-1])
        ranked = sorted(score.values(), key=lambda x: (-x["support"], -x["star"]))
        for item in ranked:
            item["matched_enemies"] = matched.get(item["operator"], [])
        return ranked[:top_n]
