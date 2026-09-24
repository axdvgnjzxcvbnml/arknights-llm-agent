"""arknights-llm-agent 后端 HTTP API（FastAPI）。

三类接口（供前端/可视化使用）：

1. 知识工具 HTTP 化（复用 MCP 的纯函数层 ``knowledge.mcp_tools.tools_*``）：
   - GET /api/operator/{name}
   - GET /api/skill/{operator}/{skill_name}
   - GET /api/enemy/{name}?level=
   - GET /api/stage/{stage_id}
   - GET /api/search?q=&k=5&doc_type=
   - GET /api/recommend/{stage_id}?...约束参数
   返回体沿用 MCP 输出契约：每个响应都带 found/evidence/message/source_url。
   * fact：PRTS 结构化事实；retrieved：RAG 检索参考资料（非事实）；inferred：规则推断（非官方结论）。

2. 对局日志（EpisodeLog JSON）：
   - GET /api/episode/{id}         一局摘要（状态/动作/理由/耗时/奖励）
   - GET /api/episode/{id}/steps   逐步明细

3. 知识图谱（NetworkX 只读）：
   - GET /api/graph/overview         节点/边统计
   - GET /api/graph/node/{node_id}   节点详情 + 邻居（node_id 形如 operator:能天使）
   - GET /api/graph/subgraph/{stage_id}  某关卡子图（关卡-敌人-推荐干员）

设计约束：
- 不 import FastMCP 的 ``knowledge/mcp_tools/server.py``（会拉起 mcp 依赖），只调 tools_* 纯函数。
- 重资源（PRTS JSON / 图谱 graphml / 向量库）全部懒加载；import 本模块不拉起 GPU/重数据栈。
- 依赖注入：``create_app(knowledge_service=, graph=, episodes=)``，测试用 mock 即可，不碰真实数据。
- CORS 允许本机开发服务器（localhost / 127.0.0.1 任意端口）。

启动：
    uvicorn api.server:app --reload --port 8000
    python -m api.server          # 等价，端口可用 ARK_API_PORT 覆盖
交互式文档：http://127.0.0.1:8000/docs （OpenAPI）
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from knowledge.mcp_tools import tools_enemy, tools_guide, tools_operator, tools_stage

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_EPISODE_DIR = os.path.join("results", "episodes")
# 节点邻居/关卡子图的规模上限，防止超密 COUNTERS 节点把响应撑爆
NODE_NEIGHBOR_CAP = 200
STAGE_OPERATOR_CAP = 50
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


# ---------------------------------------------------------------------------
# 图谱 provider（真实实现，GraphQuery 懒加载；测试可注入替身）
# ---------------------------------------------------------------------------

class GraphUnavailable(RuntimeError):
    """知识图谱文件缺失/尚未构建时抛出（HTTP 层映射为 503）。"""


def _json_safe(value):
    # type: (Any) -> Any
    """networkx 读出的图属性含 numpy 标量/None，统一转成 JSON 可序列化类型。"""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, bool)) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return str(value)


class NetworkXGraphProvider(object):
    """基于 knowledge.graph.query_graph.GraphQuery 的只读图谱访问。

    GraphQuery 构造会加载约 83M 的 graphml（首查约 9s），因此**懒加载**：
    import 本模块/构造本对象都不读盘，只有真正请求图谱接口时才加载。
    """

    def __init__(self, config_path=None):
        # type: (Optional[str]) -> None
        self.config_path = config_path
        self._gq = None
        self._tried = False

    def _ensure(self):
        if self._gq is not None:
            return self._gq
        if self._tried:
            raise GraphUnavailable("知识图谱未构建或文件缺失，请先运行 scripts/build_graph.sh")
        self._tried = True
        try:
            from knowledge.graph.query_graph import GraphQuery
            if self.config_path:
                self._gq = GraphQuery(config_path=self.config_path)
            else:
                self._gq = GraphQuery()
        except FileNotFoundError as exc:
            raise GraphUnavailable(
                "知识图谱文件缺失（%s）；请先运行 scripts/build_graph.sh 构建。" % exc)
        return self._gq

    # -- overview ---------------------------------------------------------
    def overview(self):
        # type: () -> Dict[str, Any]
        gq = self._ensure()
        stats = gq.stats()  # {"nodes": {kind: n}, "edges": {relation: n}}
        node_kinds = stats.get("nodes", {})
        edge_rels = stats.get("edges", {})
        return {
            "found": True,
            "evidence": "fact",
            "node_kinds": _json_safe(node_kinds),
            "edge_relations": _json_safe(edge_rels),
            "total_nodes": int(sum(int(v) for v in node_kinds.values())),
            "total_edges": int(sum(int(v) for v in edge_rels.values())),
            "note": "图谱规模来自本地 NetworkX 构建；COUNTERS/RECOMMENDS 边为规则推断(inferred)。",
        }

    # -- node detail ------------------------------------------------------
    def node(self, node_id):
        # type: (str) -> Optional[Dict[str, Any]]
        gq = self._ensure()
        g = gq.graph
        if node_id not in g:
            return None
        attrs = dict(g.nodes[node_id])
        neighbors = []  # type: List[Dict[str, Any]]

        def _brief(nid):
            d = g.nodes[nid]
            return {"kind": d.get("kind", ""), "name": d.get("name", "")}

        for _, dst, data in g.out_edges(node_id, data=True):
            item = {"node_id": dst, "relation": data.get("relation", ""),
                    "direction": "out"}
            item.update(_brief(dst))
            neighbors.append(item)
        for src, _, data in g.in_edges(node_id, data=True):
            item = {"node_id": src, "relation": data.get("relation", ""),
                    "direction": "in"}
            item.update(_brief(src))
            neighbors.append(item)
        truncated = len(neighbors) > NODE_NEIGHBOR_CAP
        return {
            "found": True,
            "evidence": "fact",
            "node_id": node_id,
            "attrs": _json_safe(attrs),
            "neighbor_count": len(neighbors),
            "neighbors_shown": min(len(neighbors), NODE_NEIGHBOR_CAP),
            "neighbors_truncated": truncated,
            "neighbors": _json_safe(neighbors[:NODE_NEIGHBOR_CAP]),
        }

    # -- stage subgraph ---------------------------------------------------
    def stage_subgraph(self, stage_id):
        # type: (str) -> Optional[Dict[str, Any]]
        gq = self._ensure()
        g = gq.graph
        sid = "stage:%s" % stage_id
        if sid not in g:
            return None
        node_ids = set([sid])
        edges = []  # type: List[Dict[str, Any]]
        enemies = 0
        ops = 0
        op_truncated = False
        for _, dst, data in g.out_edges(sid, data=True):
            rel = data.get("relation", "")
            if rel == "CONTAINS_ENEMY":
                node_ids.add(dst)
                enemies += 1
                edges.append({"source": sid, "target": dst, "relation": rel,
                              "count": data.get("count", ""), "level": data.get("level", ""),
                              "evidence": data.get("evidence", "fact")})
            elif rel == "RECOMMENDS":
                if ops >= STAGE_OPERATOR_CAP:
                    op_truncated = True
                    continue
                node_ids.add(dst)
                ops += 1
                edges.append({"source": sid, "target": dst, "relation": rel,
                              "support": data.get("support", 0),
                              "score": data.get("score", 0.0),
                              "evidence": "inferred"})

        nodes = []
        for nid in node_ids:
            d = g.nodes[nid]
            nodes.append({"node_id": nid, "kind": d.get("kind", ""),
                          "name": d.get("name", ""),
                          "class": d.get("class", ""),
                          "star": d.get("star", None)})
        return {
            "found": True,
            "evidence": "fact",
            "stage_id": stage_id,
            "stage_title": g.nodes[sid].get("title", stage_id),
            "enemy_count": enemies,
            "operator_count": ops,
            "operators_truncated": op_truncated,
            "operator_cap": STAGE_OPERATOR_CAP,
            "nodes": _json_safe(nodes),
            "edges": _json_safe(edges),
            "note": "CONTAINS_ENEMY 为 fact；RECOMMENDS 为规则推断(inferred)，非 PRTS 官方结论。",
        }


# ---------------------------------------------------------------------------
# 对局日志存储（results/episodes/<id>.json）
# ---------------------------------------------------------------------------

class EpisodeStore(object):
    """对局日志 JSON 存储。一个文件对应一局：``<dir>/<id>.json``。

    文件内容为 ``env.arknights_env.EpisodeLog.model_dump()``。
    目录可由外部（Env/脚本）写入；本类只做只读查询与可选保存。
    """

    def __init__(self, directory=DEFAULT_EPISODE_DIR):
        # type: (str) -> None
        self.directory = directory

    @staticmethod
    def _check_id(episode_id):
        # type: (str) -> str
        if not _SAFE_ID.match(episode_id or ""):
            raise HTTPException(status_code=400, detail="非法 episode id（仅允许字母数字 _ -）")
        return episode_id

    def _path(self, episode_id):
        return os.path.join(self.directory, self._check_id(episode_id) + ".json")

    def exists(self, episode_id):
        # type: (str) -> bool
        return os.path.isfile(self._path(episode_id))

    def get(self, episode_id):
        # type: (str) -> Optional[Dict[str, Any]]
        path = self._path(episode_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_ids(self):
        # type: () -> List[str]
        if not os.path.isdir(self.directory):
            return []
        out = []
        for fn in os.listdir(self.directory):
            if fn.endswith(".json"):
                out.append(fn[:-len(".json")])
        return sorted(out)

    def save(self, episode_id, data):
        # type: (str, Dict[str, Any]) -> str
        self._check_id(episode_id)
        os.makedirs(self.directory, exist_ok=True)
        path = self._path(episode_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path


# ---------------------------------------------------------------------------
# 序列化与依赖
# ---------------------------------------------------------------------------

def _dump(model):
    # type: (Any) -> Dict[str, Any]
    """Pydantic 输出模型 -> dict（by_alias，保留 class/type 等别名字段）。"""
    if hasattr(model, "model_dump"):
        return model.model_dump(by_alias=True)
    if isinstance(model, dict):
        return model
    raise TypeError("无法序列化 %r" % type(model).__name__)


# ---------------------------------------------------------------------------
# App 工厂
# ---------------------------------------------------------------------------

def create_app(knowledge_service=None, graph=None, episodes=None):
    # type: (Any, Any, Optional[EpisodeStore]) -> FastAPI
    """构造 API 应用。

    :param knowledge_service: KnowledgeService（或其 mock）。None 时用真实服务，
        PRTS/RAG/图谱数据懒加载，缺失时工具自行返回 found=False。
    :param graph: 图谱 provider（需有 overview/node/stage_subgraph 方法）。None 时用
        NetworkXGraphProvider（懒加载 graphml）。
    :param episodes: EpisodeStore；None 时指向 results/episodes。
    """
    app = FastAPI(
        title="arknights-llm-agent API",
        version="0.1.0",
        description="明日方舟 AI Agent 后端：知识工具（fact/retrieved/inferred 分级）、"
                    "对局日志、知识图谱。交互式文档见 /docs。",
    )

    # 本机前端开发：允许 localhost / 127.0.0.1 任意端口（http/https）
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # knowledge_service 构造廉价（数据懒加载），缺省直接实例化真实服务
    if knowledge_service is None:
        from knowledge.mcp_tools.service import KnowledgeService
        knowledge_service = KnowledgeService()
    if graph is None:
        graph = NetworkXGraphProvider()
    if episodes is None:
        episodes = EpisodeStore()
    app.state.knowledge_service = knowledge_service
    app.state.graph = graph
    app.state.episodes = episodes

    # ----------------------------- 健康检查 -----------------------------
    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok", "service": "arknights-llm-agent", "version": "0.1.0"}

    # --------------------------- 知识工具路由 ---------------------------
    @app.get("/api/operator/{name}", tags=["knowledge"])
    def api_operator(name: str, request: Request):
        out = tools_operator.query_operator(name, service=request.app.state.knowledge_service)
        return _dump(out)

    @app.get("/api/skill/{operator}/{skill_name}", tags=["knowledge"])
    def api_skill(operator: str, skill_name: str, request: Request):
        out = tools_operator.query_skill(operator, skill_name,
                                         service=request.app.state.knowledge_service)
        return _dump(out)

    @app.get("/api/enemy/{name}", tags=["knowledge"])
    def api_enemy(name: str, request: Request, level: Optional[int] = Query(None, ge=0)):
        out = tools_enemy.query_enemy(name, level=level,
                                      service=request.app.state.knowledge_service)
        return _dump(out)

    @app.get("/api/stage/{stage_id}", tags=["knowledge"])
    def api_stage(stage_id: str, request: Request):
        out = tools_stage.query_stage(stage_id, service=request.app.state.knowledge_service)
        return _dump(out)

    @app.get("/api/search", tags=["knowledge"])
    def api_search(request: Request,
                   q: str = Query(..., description="自然语言检索问题"),
                   k: int = Query(5, ge=1, le=20, description="Top-K"),
                   doc_type: Optional[str] = Query(None, description="operator/enemy/stage/guide")):
        out = tools_guide.search_guide(q, k=k, doc_type=doc_type,
                                       service=request.app.state.knowledge_service)
        return _dump(out)

    @app.get("/api/recommend/{stage_id}", tags=["knowledge"])
    def api_recommend(stage_id: str, request: Request,
                      classes: Optional[str] = Query(None, description="职业白名单，逗号分隔"),
                      min_star: Optional[int] = Query(None, ge=1, le=6),
                      max_star: Optional[int] = Query(None, ge=1, le=6),
                      top_n: Optional[int] = Query(None, ge=1, le=30),
                      exclude: Optional[str] = Query(None, description="排除干员，逗号分隔")):
        constraints = {}  # type: Dict[str, Any]
        if classes:
            constraints["classes"] = [c.strip() for c in classes.split(",") if c.strip()]
        if min_star is not None:
            constraints["min_star"] = min_star
        if max_star is not None:
            constraints["max_star"] = max_star
        if top_n is not None:
            constraints["top_n"] = top_n
        if exclude:
            constraints["exclude_operators"] = [c.strip() for c in exclude.split(",") if c.strip()]
        out = tools_stage.recommend_operators(
            stage_id, constraints=constraints or None,
            service=request.app.state.knowledge_service)
        return _dump(out)

    # --------------------------- 对局日志路由 ---------------------------
    @app.get("/api/episode/{episode_id}", tags=["episode"])
    def api_episode(episode_id: str, request: Request):
        store = request.app.state.episodes  # type: EpisodeStore
        data = store.get(episode_id)
        if data is None:
            raise HTTPException(status_code=404, detail="未找到对局：%s" % episode_id)
        steps = data.get("steps", []) if isinstance(data, dict) else []
        reward = data.get("reward") if isinstance(data, dict) else None
        total = None
        if isinstance(reward, dict):
            total = reward.get("total")
        return {
            "id": episode_id,
            "found": True,
            "stage_id": data.get("stage_id", ""),
            "outcome": data.get("outcome", ""),
            "backend": data.get("backend", ""),
            "duration_sec": data.get("duration_sec", 0.0),
            "step_count": len(steps),
            "total_reward": total,
            "reward": reward,
            "episode": data,
        }

    @app.get("/api/episode/{episode_id}/steps", tags=["episode"])
    def api_episode_steps(episode_id: str, request: Request):
        store = request.app.state.episodes  # type: EpisodeStore
        data = store.get(episode_id)
        if data is None:
            raise HTTPException(status_code=404, detail="未找到对局：%s" % episode_id)
        steps = data.get("steps", []) if isinstance(data, dict) else []
        return {"id": episode_id, "found": True, "step_count": len(steps), "steps": steps}

    # --------------------------- 知识图谱路由 ---------------------------
    @app.get("/api/graph/overview", tags=["graph"])
    def api_graph_overview(request: Request):
        try:
            return request.app.state.graph.overview()
        except GraphUnavailable as exc:
            return JSONResponse(status_code=503,
                                content={"found": False, "evidence": "fact",
                                         "message": str(exc)})

    @app.get("/api/graph/node/{node_id}", tags=["graph"])
    def api_graph_node(node_id: str, request: Request):
        try:
            out = request.app.state.graph.node(node_id)
        except GraphUnavailable as exc:
            return JSONResponse(status_code=503,
                                content={"found": False, "evidence": "fact",
                                         "message": str(exc)})
        if out is None:
            raise HTTPException(status_code=404, detail="未找到图谱节点：%s" % node_id)
        return out

    @app.get("/api/graph/subgraph/{stage_id}", tags=["graph"])
    def api_graph_subgraph(stage_id: str, request: Request):
        try:
            out = request.app.state.graph.stage_subgraph(stage_id)
        except GraphUnavailable as exc:
            return JSONResponse(status_code=503,
                                content={"found": False, "evidence": "fact",
                                         "message": str(exc)})
        if out is None:
            raise HTTPException(status_code=404, detail="未找到关卡子图：%s" % stage_id)
        return out

    return app


# 默认应用（uvicorn api.server:app）
app = create_app()


def _main():
    import uvicorn
    host = os.environ.get("ARK_API_HOST", "127.0.0.1")
    port = int(os.environ.get("ARK_API_PORT", "8000"))
    uvicorn.run("api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    _main()
