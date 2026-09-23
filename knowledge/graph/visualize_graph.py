"""知识图谱可视化：导出答辩展示用图谱概览图（matplotlib + NetworkX）。

生成两张 PNG 到 results/figures/：
- graph_overview.png  全图概览：节点按 4 类着色；fact 边（HAS_SKILL/CONTAINS_ENEMY）
                      为骨架，RECOMMENDS 为虚线，COUNTERS 用极淡线表示密度
- graph_<code>_focus.png  单关聚焦子图：关卡 -> 本关敌人 -> 克制干员（Top-N），
                      直观展示"看敌情-推克制-给推荐"的决策链路

中文字体优先使用系统 Noto Sans CJK；缺失时给出明确提示。
# TODO-V100: 无 GPU 依赖；需要交互式浏览时可在 V100 环境改用 pyvis 输出 HTML。

CLI:
    python -m knowledge.graph.visualize_graph                 # 全图 + 默认聚焦 3-8
    python -m knowledge.graph.visualize_graph --focus 10-17
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")  # 无显示环境也能出图
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

import networkx as nx

from ..rag.config import DEFAULT_CONFIG_PATH, load_knowledge_config
from .query_graph import GraphQuery

__all__ = ["visualize_overview", "visualize_focus"]

# 节点配色（4 类）
NODE_COLORS = {
    "operator": "#4C78A8",  # 蓝
    "skill": "#72B7B2",     # 青
    "enemy": "#E45756",     # 红
    "stage": "#F58518",     # 橙
}
NODE_LABEL_ZH = {"operator": "干员", "skill": "技能", "enemy": "敌人", "stage": "关卡"}

# 边配色
EDGE_COLORS = {
    "HAS_SKILL": "#72B7B2",
    "CONTAINS_ENEMY": "#E45756",
    "COUNTERS": "#9D9D9D",
    "RECOMMENDS": "#F58518",
}
EDGE_LABEL_ZH = {
    "HAS_SKILL": "干员-拥有-技能(fact)",
    "CONTAINS_ENEMY": "关卡-包含-敌人(fact)",
    "COUNTERS": "干员-克制-敌人(inferred)",
    "RECOMMENDS": "关卡-推荐-干员(inferred)",
}

CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
)


def _setup_cjk_font():
    # type: () -> str
    """注册中文字体，返回 matplotlib 可用字体名；找不到则返回默认字体。"""
    for path in CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    print("[viz] 警告：未找到 Noto Sans CJK 字体，中文可能显示为方框")
    return "DejaVu Sans"


def _edge_relation(g, u, v, key):
    return g.get_edge_data(u, v, key=key).get("relation")


def visualize_overview(gq, out_path, seed=42):
    # type: (GraphQuery, str, int) -> str
    """全图概览。COUNTERS 边过多（~900），用极淡细线表示密度，保证其他结构可读。"""
    g = gq.graph
    pos = nx.spring_layout(g, k=0.42, seed=seed, iterations=60)

    fig, ax = plt.subplots(figsize=(18, 14), dpi=150)
    ax.set_title("明日方舟知识图谱概览（%d 节点 / %d 边）"
                 % (g.number_of_nodes(), g.number_of_edges()), fontsize=20)

    # 先画 COUNTERS（最淡），再 RECOMMENDS，再 fact 边
    draw_order = ("COUNTERS", "RECOMMENDS", "CONTAINS_ENEMY", "HAS_SKILL")
    styles = {
        "COUNTERS": {"alpha": 0.05, "width": 0.4, "style": "solid"},
        "RECOMMENDS": {"alpha": 0.55, "width": 1.1, "style": "dashed"},
        "CONTAINS_ENEMY": {"alpha": 0.5, "width": 0.9, "style": "solid"},
        "HAS_SKILL": {"alpha": 0.45, "width": 0.8, "style": "solid"},
    }
    for rel in draw_order:
        edges = [(u, v, k) for u, v, k, d in g.edges(keys=True, data=True)
                 if d.get("relation") == rel]
        if not edges:
            continue
        st = styles[rel]
        nx.draw_networkx_edges(
            g, pos, edgelist=edges, ax=ax, edge_color=EDGE_COLORS[rel],
            alpha=st["alpha"], width=st["width"], style=st["style"],
            arrows=False,
        )

    # 节点
    for kind, color in NODE_COLORS.items():
        nodes = [n for n, d in g.nodes(data=True) if d.get("kind") == kind]
        if not nodes:
            continue
        size = {"stage": 130, "operator": 70, "enemy": 55, "skill": 18}[kind]
        nx.draw_networkx_nodes(g, pos, nodelist=nodes, ax=ax,
                               node_color=color, node_size=size, alpha=0.9,
                               linewidths=0.3, edgecolors="white")

    # 只标注关卡（24 个，稀疏可读），其余类型不标文字避免糊成一团
    stage_labels = {n: g.nodes[n].get("code", n)
                    for n, d in g.nodes(data=True) if d.get("kind") == "stage"}
    nx.draw_networkx_labels(g, pos, labels=stage_labels, ax=ax,
                            font_size=8, font_color="#7a3d00")

    node_handles = [Line2D([0], [0], marker="o", color="w",
                           markerfacecolor=c, markersize=11, label=NODE_LABEL_ZH[k])
                    for k, c in NODE_COLORS.items()]
    edge_handles = [Line2D([0], [0], color=EDGE_COLORS[r],
                           lw=2 if r != "COUNTERS" else 1,
                           alpha=0.8 if r != "COUNTERS" else 0.4,
                           linestyle="--" if r == "RECOMMENDS" else "-",
                           label=EDGE_LABEL_ZH[r])
                    for r in ("HAS_SKILL", "CONTAINS_ENEMY", "RECOMMENDS", "COUNTERS")]
    ax.legend(handles=node_handles + edge_handles, loc="upper left",
              fontsize=11, framealpha=0.9)
    ax.axis("off")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


def visualize_focus(gq, code, out_path, top_n_counters=3, seed=7):
    # type: (GraphQuery, str, str, int, int) -> str
    """单关聚焦子图：关卡 -> 本关敌人 -> 每个敌人 Top-N 克制干员 -> 干员技能。"""
    g = gq.graph
    stage_id = "stage:%s" % code
    if stage_id not in g:
        raise KeyError("图谱中不存在关卡 %s" % code)

    keep = {stage_id}
    enemy_ids = []
    for _, eid, d in g.out_edges(stage_id, data=True):
        if d.get("relation") == "CONTAINS_ENEMY":
            keep.add(eid)
            enemy_ids.append(eid)

    # 每个敌人取 weight 最高的 Top-N 克制干员（同权重按星级降序，与推荐排序口径一致，
    # 避免并列时取到字典序靠前的低星机器人干员）；再纳入这些干员的技能节点
    op_weights = {}
    for eid in enemy_ids:
        cands = []
        for src, _, d in g.in_edges(eid, data=True):
            if d.get("relation") == "COUNTERS":
                star = int(g.nodes[src].get("star", -1) or -1)
                cands.append((src, float(d.get("weight", 0.0)), star))
        cands.sort(key=lambda x: (-x[1], -x[2]))
        for src, w, _ in cands[:top_n_counters]:
            keep.add(src)
            op_weights[src] = max(op_weights.get(src, 0.0), w)

    for op in list(op_weights.keys()):
        for _, sid, d in g.out_edges(op, data=True):
            if d.get("relation") == "HAS_SKILL":
                keep.add(sid)

    sub = g.subgraph(keep).copy()
    # spring 布局并拉大节点间距，避免多个干员/技能节点对称重叠
    pos = nx.spring_layout(sub, k=1.4, seed=seed, iterations=120)

    fig, ax = plt.subplots(figsize=(17, 12), dpi=150)
    ax.set_title("关卡 %s 决策子图：敌情 → 克制 → 干员技能（克制干员取每敌 Top%d）"
                 % (code, top_n_counters), fontsize=18)

    rel_styles = {
        "HAS_SKILL": (EDGE_COLORS["HAS_SKILL"], 0.9, 1.0, "-"),
        "CONTAINS_ENEMY": (EDGE_COLORS["CONTAINS_ENEMY"], 0.9, 1.6, "-"),
        "COUNTERS": (EDGE_COLORS["COUNTERS"], 0.7, 1.0, "-"),
        "RECOMMENDS": (EDGE_COLORS["RECOMMENDS"], 0.8, 1.4, "--"),
    }
    for rel, (color, alpha, width, style) in rel_styles.items():
        edges = [(u, v) for u, v, d in sub.edges(data=True) if d.get("relation") == rel]
        if edges:
            nx.draw_networkx_edges(sub, pos, edgelist=edges, ax=ax,
                                   edge_color=color, alpha=alpha, width=width,
                                   style=style, arrows=True,
                                   arrowsize=12, node_size=300)

    for kind, color in NODE_COLORS.items():
        nodes = [n for n, d in sub.nodes(data=True) if d.get("kind") == kind]
        if not nodes:
            continue
        size = {"stage": 1600, "operator": 420, "enemy": 320, "skill": 120}[kind]
        nx.draw_networkx_nodes(sub, pos, nodelist=nodes, ax=ax,
                               node_color=color, node_size=size, alpha=0.92,
                               edgecolors="white", linewidths=1.0)

    labels = {}
    for n, d in sub.nodes(data=True):
        kind = d.get("kind")
        if kind == "stage":
            labels[n] = code
        elif kind in ("operator", "enemy"):
            labels[n] = d.get("name", n)
        elif kind == "skill":
            labels[n] = d.get("name", "")
    nx.draw_networkx_labels(sub, pos, labels=labels, ax=ax, font_size=9)

    handles = [Line2D([0], [0], color=EDGE_COLORS[r], lw=2,
                      linestyle="--" if r == "RECOMMENDS" else "-",
                      label=EDGE_LABEL_ZH[r])
               for r in ("CONTAINS_ENEMY", "COUNTERS", "HAS_SKILL", "RECOMMENDS")
               if any(d.get("relation") == r for _, _, d in sub.edges(data=True))]
    ax.legend(handles=handles, loc="upper left", fontsize=11, framealpha=0.9)
    ax.axis("off")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="知识图谱可视化")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out-dir", default="results/figures")
    parser.add_argument("--focus", default=None,
                        help="额外聚焦的关卡编号；默认输出 3-8（纯敌情）与 4-7（完整克制链）")
    parser.add_argument("--top-n", type=int, default=3, help="每敌人取前 N 个克制干员")
    args = parser.parse_args(argv)

    _setup_cjk_font()
    config = load_knowledge_config(args.config)
    gq = GraphQuery(config=config)

    p1 = visualize_overview(gq, os.path.join(args.out_dir, "graph_overview.png"))
    print("[viz] 全图概览: %s" % p1)

    # 默认两张聚焦图：3-8 敌人无类型弱点（只有 fact 敌情边，展示规则不无中生有）；
    # 4-7 有法抗 50 的高抗敌人（展示 敌情→克制→干员→技能 完整决策链）。
    focus_codes = [args.focus] if args.focus else ["3-8", "4-7"]
    for code in focus_codes:
        safe_code = code.replace("/", "_").replace(" ", "_")
        out_path = os.path.join(args.out_dir, "graph_%s_focus.png" % safe_code)
        visualize_focus(gq, code, out_path, top_n_counters=args.top_n)
        print("[viz] 聚焦子图 %s: %s" % (code, out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
