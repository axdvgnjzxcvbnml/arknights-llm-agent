"""后端 API 单元测试（全 mock，不依赖真实数据/GPU）。

覆盖：
- 每个接口的 200 / 未命中(found:false) / 400 / 404 / 422
- JSON 别名序列化（class / type）与 evidence 分级
- CORS 正则（localhost / 127.0.0.1 任意端口）
- EpisodeStore 的目录穿越防护与读写
- import 轻量：import api.server 不拉起 torch/transformers/chromadb/bge/mcp
"""

import json
import os
import re
import tempfile

import pytest
from fastapi.testclient import TestClient

from api.server import EpisodeStore, create_app


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app)


class FakeKnowledgeService(object):
    """最小假服务：operator/skill/enemy/stage/search/recommend 全部命中或未命中。"""

    def __init__(self, missing=None):
        self.missing = set(missing or [])

    def get_operator(self, name):
        if name in self.missing:
            return None
        return {"name": name, "display_name": name, "star_rating": 6,
                "operator_class": "狙击", "branch": "速射手",
                "position": "远程", "deploy_cost": "12",
                "trait": {"branch": "速射手", "desc": "优先攻击空中单位"},
                "skills": [{"name": "过载模式", "type": "攻击回复",
                             "levels": [{"level": "10", "cost": "自动触发",
                                         "duration": "15秒"}]}],
                "source_url": "https://prts.wiki/w/%s" % name}

    def get_skill(self, operator, skill_name):
        if operator in self.missing:
            return None
        return {"operator": operator, "skill": self.get_operator(operator)["skills"][0]}

    def get_enemy(self, name, level=None):
        if name in self.missing:
            return None
        return {"name": name, "levels": [{"level": 0, "hp": 1000, "atk": 100,
                                           "defense": 50, "resistance": 0}]}

    def get_stage(self, stage_id):
        if stage_id in self.missing:
            return None
        return {"code": stage_id, "info": {"name": "黄昏"},
                "enemies": [{"name": "碎骨", "count": "1", "level": "0",
                              "position": "", "stats": {}}]}

    def search(self, query, k=5, doc_type=None):
        if not query.strip():
            return None
        return {"query": query, "k": k, "doc_type": doc_type,
                "hits": [{"content": "片段", "score": 0.8, "source": "能天使",
                           "doc_type": "operator", "section": "skill",
                           "url": "https://prts.wiki/w/能天使",
                           "evidence": "retrieved"}],
                "embedding_backend": "bge-small-zh-v1.5",
                "note": "参考"}

    def recommend(self, stage_id, **kw):
        if stage_id in self.missing:
            return None
        return {"stage_id": stage_id, "constraints_applied": kw,
                "operators": [{"operator": "艾雅法拉", "operator_class": "术师",
                                "star_rating": 6, "score": 3.2,
                                "matched_enemies": ["碎骨"],
                                "matched_rules": ["high_resistance->caster"],
                                "evidence": "inferred"}]}


class FakeGraphProvider(object):
    """最小假图谱：overview / node / subgraph 全命中或缺失。"""

    def __init__(self, missing=None):
        self.missing = set(missing or [])

    def overview(self):
        return {"node_kinds": {"operator": 1, "enemy": 1, "stage": 1, "skill": 1},
                "edge_relations": {"COUNTERS": 1, "HAS_SKILL": 1,
                                    "CONTAINS_ENEMY": 1, "RECOMMENDS": 1},
                "total_nodes": 4, "total_edges": 4}

    def node(self, node_id):
        if node_id in self.missing:
            return None
        return {"node_id": node_id, "attrs": {"kind": "operator", "name": "能天使",
                                               "class": "狙击", "star": 6},
                "neighbors": [{"node_id": "skill:过载模式",
                                "relation": "HAS_SKILL", "direction": "out",
                                "kind": "skill", "name": "过载模式"}],
                "neighbor_count": 1, "neighbors_shown": 1,
                "neighbors_truncated": False}

    def subgraph(self, stage_id):
        if stage_id in self.missing:
            return None
        return {"stage_id": stage_id, "stage_title": "黄昏",
                "enemy_count": 1, "operator_count": 0,
                "nodes": [{"node_id": "stage:%s" % stage_id, "kind": "stage",
                            "name": "黄昏"}],
                "edges": []}


def _make_client(ks=None, gp=None, episodes=None):
    app = create_app(knowledge_service=ks or FakeKnowledgeService(),
                     graph_provider=gp or FakeGraphProvider(),
                     episode_store=episodes)
    return TestClient(app)


# ---------- operator ----------

def test_operator_ok(client):
    r = client.get("/api/operator/能天使")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["evidence"] == "fact"
    assert body["name"] == "能天使"
    assert body["class"] == "狙击"       # 别名
    assert "skills" in body


def test_operator_missing(client):
    r = client.get("/api/operator/不存在干员")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is False
    assert "message" in body


def test_operator_empty_name(client):
    r = client.get("/api/operator/")
    assert r.status_code in (404, 200)  # 空路径由路由层兜底，不 500


# ---------- skill ----------

def test_skill_ok(client):
    r = client.get("/api/skill/能天使/过载模式")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["evidence"] == "fact"
    assert body["operator"] == "能天使"
    assert body["skill"]["name"] == "过载模式"


def test_skill_missing_operator(client):
    r = client.get("/api/skill/不存在/过载模式")
    assert r.status_code == 200
    assert r.json()["found"] is False


def test_skill_missing_name(client):
    r = client.get("/api/skill/能天使/不存在的技能")
    assert r.status_code == 200
    assert r.json()["found"] is False


# ---------- enemy ----------

def test_enemy_ok(client):
    r = client.get("/api/enemy/碎骨")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["evidence"] == "fact"
    assert body["levels"][0]["level"] == 0


def test_enemy_with_level(client):
    r = client.get("/api/enemy/碎骨?level=0")
    assert r.status_code == 200
    assert r.json()["found"] is True


def test_enemy_bad_level(client):
    r = client.get("/api/enemy/碎骨?level=-1")
    assert r.status_code == 422


def test_enemy_missing(client):
    r = client.get("/api/enemy/不存在敌人")
    assert r.status_code == 200
    assert r.json()["found"] is False


# ---------- stage ----------

def test_stage_ok(client):
    r = client.get("/api/stage/3-8")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["evidence"] == "fact"
    assert body["enemies"][0]["name"] == "碎骨"


def test_stage_missing(client):
    r = client.get("/api/stage/99-99")
    assert r.status_code == 200
    assert r.json()["found"] is False


# ---------- search ----------

def test_search_ok(client):
    r = client.get("/api/search?q=能天使的技能&k=5&doc_type=operator")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["evidence"] == "retrieved"
    assert body["hits"][0]["type"] == "operator"   # 别名
    assert body["hits"][0]["evidence"] == "retrieved"


def test_search_k_range(client):
    assert client.get("/api/search?q=x&k=99").status_code == 422
    assert client.get("/api/search?q=x&k=0").status_code == 422
    assert client.get("/api/search?q=x&k=5").status_code == 200


def test_search_missing_q(client):
    r = client.get("/api/search")
    assert r.status_code == 422


def test_search_empty_hits(client):
    ks = FakeKnowledgeService(missing={""})
    c = _make_client(ks=ks)
    r = c.get("/api/search?q=")
    assert r.status_code == 422


# ---------- recommend ----------

def test_recommend_ok(client):
    r = client.get("/api/recommend/3-8?classes=术师,狙击&min_star=5&top_n=8")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["evidence"] == "inferred"
    assert body["operators"][0]["class"] == "术师"   # 别名
    assert body["operators"][0]["evidence"] == "inferred"


def test_recommend_missing_stage(client):
    r = client.get("/api/recommend/99-99")
    assert r.status_code == 200
    assert r.json()["found"] is False


def test_recommend_bad_top_n(client):
    r = client.get("/api/recommend/3-8?top_n=0")
    assert r.status_code == 422
    assert client.get("/api/recommend/3-8?top_n=31").status_code == 422


def test_recommend_bad_star(client):
    assert client.get("/api/recommend/3-8?min_star=0").status_code == 422
    assert client.get("/api/recommend/3-8?max_star=7").status_code == 422


# ---------- episode ----------

def test_episode_roundtrip(tmp_path):
    store = EpisodeStore(str(tmp_path))
    store.save("ep-win", {"stage_id": "3-8", "outcome": "win",
                           "steps": [{"step": 0}], "reward": {"total": 87.0}})
    data = store.load("ep-win")
    assert data["outcome"] == "win"
    assert data["reward"]["total"] == 87.0
    assert os.path.isfile(os.path.join(str(tmp_path), "ep-win.json"))


def test_episode_id_whitelist(tmp_path):
    store = EpisodeStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.save("../evil", {})
    with pytest.raises(ValueError):
        store.save("a/b", {})
    with pytest.raises(ValueError):
        store.save("a\x00b", {})


def test_episode_missing(client):
    r = client.get("/api/episode/no-such-ep")
    assert r.status_code == 404


def test_episode_bad_id(client):
    r = client.get("/api/episode/../x")
    assert r.status_code == 400


def test_episode_steps(client, tmp_path):
    store = EpisodeStore(str(tmp_path))
    store.save("ep", {"stage_id": "3-8", "outcome": "win",
                      "steps": [{"step": 0, "elapsed_sec": 1.0, "cost": 15,
                                  "life": 3, "state_text": "s", "plan": {"actions": []},
                                  "decision_summary": "d", "decision_analysis": [],
                                  "evidence": ["fact"], "step_reward": 0.0,
                                  "latency_ms": {"perceive": 1.0, "slow": 2.0, "act": 0.5}}]})
    app = create_app(episode_store=store)
    c = TestClient(app)
    r = c.get("/api/episode/ep/steps")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["step_count"] == 1
    assert body["steps"][0]["step"] == 0
    assert body["steps"][0]["latency_ms"]["slow"] == 2.0


# ---------- graph ----------

def test_graph_overview(client):
    r = client.get("/api/graph/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["evidence"] == "fact"
    assert body["total_nodes"] == 4


def test_graph_node_ok(client):
    r = client.get("/api/graph/node/operator:能天使")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["neighbors"][0]["relation"] == "HAS_SKILL"
    assert body["neighbors_truncated"] is False


def test_graph_node_missing(client):
    r = client.get("/api/graph/node/enemy:不存在")
    assert r.status_code == 404


def test_graph_subgraph_ok(client):
    r = client.get("/api/graph/subgraph/3-8")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["stage_id"] == "3-8"


def test_graph_subgraph_missing(client):
    r = client.get("/api/graph/subgraph/99-99")
    assert r.status_code == 404


# ---------- health / cors ----------

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_cors_localhost_any_port(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_127_any_port(client):
    r = client.get("/api/health", headers={"Origin": "http://127.0.0.1:8080"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:8080"


def test_cors_reject_external(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_cors_regex_compiled():
    from api.server import _CORS_ORIGIN_RE
    assert _CORS_ORIGIN_RE.match("http://localhost:1")
    assert _CORS_ORIGIN_RE.match("https://127.0.0.1:65535")
    assert not _CORS_ORIGIN_RE.match("http://localhost")
    assert not _CORS_ORIGIN_RE.match("http://evil.com")


def test_import_light():
    """import api.server 不得拉起 torch/transformers/chromadb/bge/mcp。"""
    import sys
    heavy = {"torch", "transformers", "chromadb", "sentence_transformers",
             "mcp", "fastmcp"}
    loaded = {m for m in sys.modules if m.split(".")[0] in heavy}
    assert not loaded, "api.server import 拉起了重依赖: %s" % sorted(loaded)
