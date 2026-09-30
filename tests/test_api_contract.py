# -*- coding: utf-8 -*-
"""
API 契约测试：校验实际响应是否符合 docs/api-contract.md 定义的 schema。

用 FastAPI TestClient 启动应用，对每个接口发请求，校验：
- 状态码
- 关键字段存在
- evidence 字段格式（如适用）
- 响应类型（dict/list）

数据缺失时自动 skip（不阻塞 CI）。
"""
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    """启动 FastAPI TestClient。"""
    try:
        from api.server import app
    except ImportError:
        pytest.skip("api.server 不可用")
    return TestClient(app)


def _has_data():
    """检查 PRTS 数据是否就位（operator/enemy/stage 接口需要）。"""
    import os
    return os.path.exists("data/prts_raw") and len(os.listdir("data/prts_raw")) > 0


# ---------------------------------------------------------------------------
# 通用校验工具
# ---------------------------------------------------------------------------
def _check_evidence_format(resp_json):
    """校验 evidence 字段格式（如果存在）。"""
    if "evidence" in resp_json:
        valid = {"fact", "annotated", "cv", "retrieved", "inferred", "estimated", "mock", "unknown"}
        assert resp_json["evidence"] in valid, f"evidence 值无效: {resp_json['evidence']}, 有效值: {valid}"


def _check_found_field(resp_json):
    """校验 found 字段（如果存在）。"""
    if "found" in resp_json:
        assert isinstance(resp_json["found"], bool), f"found 应为 bool, 实际: {type(resp_json['found'])}"


# ---------------------------------------------------------------------------
# 1. 系统接口
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_status(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "server_version" in data
        assert "modules" in data
        assert isinstance(data["modules"], dict)
        assert "vram" in data

    def test_health_modules_structure(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        for mod_name, mod_info in data["modules"].items():
            assert "online" in mod_info, f"模块 {mod_name} 缺少 online 字段"
            assert "evidence" in mod_info, f"模块 {mod_name} 缺少 evidence 字段"
            assert isinstance(mod_info["online"], bool)


# ---------------------------------------------------------------------------
# 2. 知识接口
# ---------------------------------------------------------------------------
class TestKnowledge:
    @pytest.mark.skipif(not _has_data(), reason="PRTS 数据未就位")
    def test_operator(self, client):
        resp = client.get("/api/operator/能天使")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        _check_evidence_format(data)
        if data["found"]:
            assert "name" in data
            assert "star_rating" in data
            assert "class" in data
            assert "skills" in data
            assert isinstance(data["skills"], list)

    def test_operator_not_found(self, client):
        resp = client.get("/api/operator/不存在的干员名12345")
        # 400 或 200(found=false) 都可接受
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            assert resp.json().get("found") is False

    @pytest.mark.skipif(not _has_data(), reason="PRTS 数据未就位")
    def test_enemy(self, client):
        resp = client.get("/api/enemy/碎骨")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        _check_evidence_format(data)
        if data["found"]:
            assert "name" in data
            assert "levels" in data
            assert isinstance(data["levels"], list)

    @pytest.mark.skipif(not _has_data(), reason="PRTS 数据未就位")
    def test_stage(self, client):
        resp = client.get("/api/stage/3-8")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        _check_evidence_format(data)
        if data["found"]:
            assert "stage_id" in data
            assert "enemies" in data

    def test_search(self, client):
        resp = client.get("/api/search", params={"q": "能天使", "k": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert "hits" in data
        assert isinstance(data["hits"], list)
        # 无 total 字段，用 len(hits) 代替
        if data["hits"]:
            hit = data["hits"][0]
            assert "content" in hit
            assert "score" in hit
            # hit 字段平铺（无 metadata 嵌套）：source/type/section/url
            assert "source" in hit
            assert "type" in hit
            _check_evidence_format(hit)

    def test_search_empty_query(self, client):
        resp = client.get("/api/search", params={"q": "", "k": 3})
        # 空查询应返回 400 或空结果，不应该 500
        assert resp.status_code in (200, 400)

    @pytest.mark.skipif(not _has_data(), reason="PRTS 数据未就位")
    def test_recommend(self, client):
        resp = client.get("/api/recommend/3-8")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        _check_evidence_format(data)
        # recommend 必须标 inferred（规则推导，非事实）
        if data["found"] and "evidence" in data:
            assert data["evidence"] == "inferred", f"recommend 必须标 inferred, 实际: {data['evidence']}"
        if "operators" in data:
            assert isinstance(data["operators"], list)


# ---------------------------------------------------------------------------
# 3. 对局接口
# ---------------------------------------------------------------------------
class TestEpisode:
    def test_episodes_list(self, client):
        resp = client.get("/api/episodes")
        assert resp.status_code == 200
        data = resp.json()
        assert "episodes" in data
        assert isinstance(data["episodes"], list)
        assert "count" in data

    def test_episode_not_found(self, client):
        resp = client.get("/api/episode/不存在的id_12345")
        # 404 或 400 或 200(found=false) 都可接受
        assert resp.status_code in (200, 400, 404)


# ---------------------------------------------------------------------------
# 4. 知识图谱接口
# ---------------------------------------------------------------------------
class TestGraph:
    def test_graph_overview(self, client):
        resp = client.get("/api/graph/overview")
        assert resp.status_code == 200
        data = resp.json()
        # 实际字段：node_kinds / edge_relations / total_nodes / total_edges
        assert "node_kinds" in data
        assert "edge_relations" in data
        assert "total_nodes" in data
        assert "total_edges" in data
        assert isinstance(data["total_nodes"], int)
        assert isinstance(data["total_edges"], int)

    @pytest.mark.skipif(not _has_data(), reason="PRTS 数据未就位")
    def test_graph_subgraph(self, client):
        resp = client.get("/api/graph/subgraph/3-8")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        if data["found"]:
            assert "nodes" in data
            assert "edges" in data
            assert isinstance(data["nodes"], list)
            assert isinstance(data["edges"], list)


# ---------------------------------------------------------------------------
# 5. 资源接口
# ---------------------------------------------------------------------------
class TestResources:
    def test_source_stone(self, client):
        resp = client.get("/api/resources/source-stone")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        # 三档结构在 tiers 下：immediate / short_term / long_term
        assert "tiers" in data
        tiers = data["tiers"]
        for tier in ("immediate", "short_term", "long_term"):
            assert tier in tiers, f"tiers 缺少 {tier}"
            assert "normal_stone" in tiers[tier], f"{tier} 缺少 normal_stone"
            assert "stages" in tiers[tier], f"{tier} 缺少 stages"
            assert isinstance(tiers[tier]["stages"], list)

    def test_account(self, client):
        resp = client.get("/api/resources/account")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        _check_evidence_format(data)
        # account 当前是 mock
        if "evidence" in data:
            assert data["evidence"] == "mock", f"account 应为 mock, 实际: {data['evidence']}"

    def test_progress(self, client):
        resp = client.get("/api/resources/progress")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        _check_evidence_format(data)


# ---------------------------------------------------------------------------
# 6. 任务接口
# ---------------------------------------------------------------------------
class TestTasks:
    def test_tasks(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        assert "current" in data
        # 实际字段：upcoming（不是 queue）
        assert "upcoming" in data
        assert isinstance(data["upcoming"], list)


# ---------------------------------------------------------------------------
# 7. 实时对局接口
# ---------------------------------------------------------------------------
class TestLive:
    def test_live_snapshot(self, client):
        resp = client.get("/api/live/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        _check_found_field(data)
        # 实际字段：ts（不是 timestamp）
        assert "ts" in data
        assert "state" in data


# ---------------------------------------------------------------------------
# 8. 训练接口
# ---------------------------------------------------------------------------
class TestTraining:
    def test_training_runs(self, client):
        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert isinstance(data["runs"], list)
        assert "connected" in data
        # CPU 侧 connected 应为 false
        assert data["connected"] is False, f"CPU 侧 connected 应为 false, 实际: {data['connected']}"

    def test_training_metrics_empty(self, client):
        """CPU 侧 training/metrics 应返回 409 空态。"""
        resp = client.get("/api/training/metrics", params={"run": "test"})
        # 409 是预期行为，也可能是 200(空列表)
        assert resp.status_code in (200, 409)


# ---------------------------------------------------------------------------
# 9. 边界输入测试
# ---------------------------------------------------------------------------
class TestBoundary:
    def test_operator_special_chars(self, client):
        """特殊字符的干员名不应导致 500。"""
        resp = client.get("/api/operator/<script>alert(1)</script>")
        assert resp.status_code in (200, 400, 404)
        assert resp.status_code != 500

    def test_stage_invalid_id(self, client):
        """非法关卡 ID 不应导致 500。"""
        resp = client.get("/api/stage/../../etc/passwd")
        assert resp.status_code in (200, 400, 404)
        assert resp.status_code != 500

    def test_search_long_query(self, client):
        """超长查询不应导致 500。"""
        long_q = "a" * 10000
        resp = client.get("/api/search", params={"q": long_q, "k": 3})
        assert resp.status_code in (200, 400)
        assert resp.status_code != 500

    def test_negative_k(self, client):
        """负数 k 不应导致 500。"""
        resp = client.get("/api/search", params={"q": "test", "k": -1})
        assert resp.status_code in (200, 400, 422)
        assert resp.status_code != 500
