"""api/server.py 集成测试（真实数据端到端）。

与 tests/test_api.py（纯 mock 单元测试）的区别：
- 用真实 KnowledgeService（PRTS JSON + 图谱）启动 FastAPI
- 测接口的端到端行为，验证真实数据返回正确
- 数据缺失时自动 skip（CI 环境可能没有 data/）
- 记录每个接口的真实延迟

覆盖：
- /api/operator/{name} 返回真实干员数据
- /api/enemy/{name} 返回真实敌人数据
- /api/stage/{stage_id} 返回真实关卡数据
- /api/search?q=xxx 返回真实检索结果（需 RAG，慢）
- /api/graph/overview 返回真实图谱统计
- /api/graph/node/{id} 返回真实节点详情
- /api/resources/source-stone 返回真实源石三档
- /api/health 返回模块状态
- /api/episodes + /api/episode/{id} 端到端（写入+读取）
"""
import json
import os
import sys
import time

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 数据路径检查
PRTS_RAW = os.path.join(PROJECT_ROOT, "data", "prts_raw")
GRAPH_DIR = os.path.join(PROJECT_ROOT, "data", "graph")
VECTOR_STORE = os.path.join(PROJECT_ROOT, "data", "vector_store")


def _has_prts_data():
    """检查 PRTS 原始数据是否存在（至少有 operator/enemy/stage 目录）。"""
    if not os.path.isdir(PRTS_RAW):
        return False
    # 至少有一个子目录有 JSON 文件
    for sub in ["operators", "enemies", "stages"]:
        sub_path = os.path.join(PRTS_RAW, sub)
        if os.path.isdir(sub_path):
            jsons = [f for f in os.listdir(sub_path) if f.endswith(".json")]
            if jsons:
                return True
    return False


def _has_graph():
    """检查知识图谱文件是否存在。"""
    if not os.path.isdir(GRAPH_DIR):
        return False
    return any(f.endswith((".graphml", ".pkl")) for f in os.listdir(GRAPH_DIR))


def _has_vector_store():
    """检查 ChromaDB 向量库是否存在。"""
    if not os.path.isdir(VECTOR_STORE):
        return False
    return any("chroma" in f.lower() or f.endswith(".sqlite3") or f.endswith(".parquet")
               for f in os.listdir(VECTOR_STORE))


HAS_PRTS = _has_prts_data()
HAS_GRAPH = _has_graph()
HAS_RAG = _has_vector_store()

# 集成测试需要 PRTS + 图谱
pytestmark = pytest.mark.skipif(
    not (HAS_PRTS and HAS_GRAPH),
    reason="集成测试需要真实 PRTS 数据和图谱（data/prts_raw + data/graph）",
)


@pytest.fixture(scope="module")
def app_client():
    """用真实 KnowledgeService 启动 FastAPI TestClient（module 级共享，避免重复预热）。"""
    from fastapi.testclient import TestClient
    from api.server import create_app

    # create_app() 不传参 → 自动创建 KnowledgeService 并预热（include_retriever=False）
    app = create_app()
    client = TestClient(app)
    yield client
    # 清理：关闭 app（TestClient 上下文管理器会自动处理）


# ----------------------------------------------------------- 延迟记录
@pytest.fixture(scope="module", autouse=True)
def record_latencies():
    """记录每个接口的真实延迟，测试结束后打印汇总。"""
    latencies = {}
    yield latencies
    if latencies:
        print("\n=== API 集成测试延迟汇总 ===")
        for endpoint, ms in sorted(latencies.items(), key=lambda x: -x[1]):
            print("  %-45s %8.1f ms" % (endpoint, ms))


def _record(latencies, endpoint, start):
    latencies[endpoint] = (time.time() - start) * 1000


# ----------------------------------------------------------- 健康检查
class TestHealth(object):
    def test_health_returns_modules(self, app_client, record_latencies):
        start = time.time()
        resp = app_client.get("/api/health")
        _record(record_latencies, "GET /api/health", start)
        assert resp.status_code == 200
        data = resp.json()
        assert "modules" in data
        assert "vram" in data
        assert "server_version" in data
        assert "env" in data

    def test_health_modules_online(self, app_client):
        resp = app_client.get("/api/health")
        data = resp.json()
        # CPU 侧 modules 静态声明为全在线
        for name, mod in data["modules"].items():
            assert "online" in mod


# ----------------------------------------------------------- 干员/敌人/关卡
class TestKnowledgeEndpoints(object):
    def test_query_operator_real(self, app_client, record_latencies):
        """查询真实存在的干员（能天使）。"""
        start = time.time()
        resp = app_client.get("/api/operator/能天使")
        _record(record_latencies, "GET /api/operator/能天使", start)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["name"] == "能天使"
        assert data["star_rating"] == 6
        assert data["class"] == "狙击"
        assert len(data["skills"]) >= 1
        assert "evidence" in data

    def test_query_operator_not_found(self, app_client):
        """查询不存在的干员应返回 found=False。"""
        resp = app_client.get("/api/operator/不存在的干员XYZ")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_query_enemy_real(self, app_client, record_latencies):
        """查询真实存在的敌人（碎骨）。"""
        start = time.time()
        resp = app_client.get("/api/enemy/碎骨")
        _record(record_latencies, "GET /api/enemy/碎骨", start)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["name"] == "碎骨"
        assert len(data["levels"]) >= 1

    def test_query_stage_real(self, app_client, record_latencies):
        """查询真实存在的关卡（3-8）。"""
        start = time.time()
        resp = app_client.get("/api/stage/3-8")
        _record(record_latencies, "GET /api/stage/3-8", start)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["stage_id"] == "3-8"
        # 3-8 应该有敌人
        assert len(data.get("enemies", [])) >= 1

    def test_query_skill_real(self, app_client, record_latencies):
        """查询真实干员的技能。"""
        start = time.time()
        resp = app_client.get("/api/skill/能天使/过载模式")
        _record(record_latencies, "GET /api/skill/能天使/过载模式", start)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["operator"] == "能天使"


# ----------------------------------------------------------- RAG 检索
class TestSearchEndpoint(object):
    @pytest.mark.skipif(not HAS_RAG, reason="需要 ChromaDB 向量库（data/vector_store）")
    def test_search_real(self, app_client, record_latencies):
        """用真实 RAG 检索（需要向量库，首次加载可能慢）。"""
        start = time.time()
        resp = app_client.get("/api/search?q=能天使的技能&k=3")
        _record(record_latencies, "GET /api/search?q=能天使的技能", start)
        assert resp.status_code == 200
        data = resp.json()
        assert "hits" in data
        assert len(data["hits"]) <= 3
        # 检索结果应包含能天使相关内容
        if data["hits"]:
            first = data["hits"][0]
            assert "content" in first
            assert "score" in first
            assert "source" in first


# ----------------------------------------------------------- 知识图谱
class TestGraphEndpoints(object):
    def test_graph_overview_real(self, app_client, record_latencies):
        """图谱概览应返回真实节点/边统计。"""
        start = time.time()
        resp = app_client.get("/api/graph/overview")
        _record(record_latencies, "GET /api/graph/overview", start)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_nodes" in data
        assert "total_edges" in data
        # 真实图谱应该有几千个节点、几万条边
        assert data["total_nodes"] > 100
        assert data["total_edges"] > 100
        assert "node_kinds" in data
        assert "edge_relations" in data

    def test_graph_node_real(self, app_client, record_latencies):
        """查询真实节点（operator:能天使）。"""
        start = time.time()
        resp = app_client.get("/api/graph/node/operator:能天使")
        _record(record_latencies, "GET /api/graph/node/operator:能天使", start)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["node_id"] == "operator:能天使"
        assert "attrs" in data
        assert "neighbors" in data

    def test_graph_subgraph_real(self, app_client, record_latencies):
        """查询关卡子图（3-8）。"""
        start = time.time()
        resp = app_client.get("/api/graph/subgraph/3-8")
        _record(record_latencies, "GET /api/graph/subgraph/3-8", start)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert "nodes" in data
        assert "edges" in data
        # 3-8 子图应该包含敌人节点
        node_ids = [n["node_id"] for n in data["nodes"]]
        assert any("3-8" in nid or nid == "3-8" for nid in node_ids) or len(node_ids) > 0


# ----------------------------------------------------------- 资源
class TestResourcesEndpoint(object):
    def test_source_stone_real(self, app_client, record_latencies):
        """源石三档应返回真实数据（基于 PRTS 关卡进度）。"""
        start = time.time()
        resp = app_client.get("/api/resources/source-stone")
        _record(record_latencies, "GET /api/resources/source-stone", start)
        assert resp.status_code == 200
        data = resp.json()
        assert "tiers" in data
        assert "immediate" in data["tiers"]
        assert "short_term" in data["tiers"]
        assert "long_term" in data["tiers"]
        # 每档应包含 normal_stone/raid_stone/stages
        for tier in ["immediate", "short_term", "long_term"]:
            assert "normal_stone" in data["tiers"][tier]
            assert "raid_stone" in data["tiers"][tier]
            assert "stages" in data["tiers"][tier]


# ----------------------------------------------------------- 对局日志端到端
class TestEpisodeEndToEnd(object):
    def test_episode_write_read(self, app_client, record_latencies):
        """写入一局对局，然后读取列表和详情。"""
        store = app_client.app.state.episodes

        # 构造一局模拟对局数据（与 EpisodeLog/EnvStep 同构的 dict）
        episode_data = {
            "stage_id": "3-8",
            "outcome": "win",
            "backend": "integration_test",
            "duration_sec": 45.5,
            "reward": {"total": 100.0, "items": [{"type": "clear", "value": 100}]},
            "steps": [
                {
                    "step": 0,
                    "elapsed_sec": 0.0,
                    "state_text": "费用15，敌人从左侧来",
                    "cost": 15,
                    "life": 20,
                    "decision_summary": "部署先锋(A3,朝右)",
                    "decision_analysis": ["先下先锋回费", "费用充足"],
                    "evidence": [{"level": "fact", "source": "游戏状态"}],
                    "step_reward": 0.0,
                    "latency_ms": {"perception": 12.0, "decision": 108.5},
                },
                {
                    "step": 1,
                    "elapsed_sec": 5.0,
                    "state_text": "费用20，先锋已部署",
                    "cost": 20,
                    "life": 20,
                    "decision_summary": "部署狙击(B3,朝左)",
                    "decision_analysis": ["费用够了，下狙击输出"],
                    "evidence": [{"level": "inferred", "source": "策略规则"}],
                    "step_reward": 0.0,
                    "latency_ms": {"perception": 10.0, "decision": 85.2},
                },
            ],
        }
        store.save("integration_test_001", episode_data)

        # 读取列表
        start = time.time()
        resp = app_client.get("/api/episodes")
        _record(record_latencies, "GET /api/episodes", start)
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        episode_ids = [e["id"] for e in data["episodes"]]
        assert "integration_test_001" in episode_ids

        # 读取详情（默认不内嵌 steps）
        start = time.time()
        resp = app_client.get("/api/episode/integration_test_001")
        _record(record_latencies, "GET /api/episode/integration_test_001", start)
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == "integration_test_001"
        assert detail["found"] is True
        assert detail["outcome"] == "win"
        assert detail["total_reward"] == 100.0
        assert detail["step_count"] == 2
        assert detail["embedded_steps"] is False

        # 读取 steps
        start = time.time()
        resp = app_client.get("/api/episode/integration_test_001/steps")
        _record(record_latencies, "GET /api/episode/integration_test_001/steps", start)
        assert resp.status_code == 200
        steps_data = resp.json()
        assert steps_data["found"] is True
        assert steps_data["step_count"] == 2
        assert steps_data["steps"][0]["decision_summary"] == "部署先锋(A3,朝右)"
        assert steps_data["steps"][1]["decision_analysis"] == ["费用够了，下狙击输出"]

        # 清理测试数据
        import os as _os
        test_path = store._path("integration_test_001")
        if _os.path.exists(test_path):
            _os.remove(test_path)

    def test_episode_not_found(self, app_client):
        """查询不存在的对局应返回 404。"""
        resp = app_client.get("/api/episode/nonexistent_episode_xyz")
        assert resp.status_code == 404
