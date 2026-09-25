"""api/server.py 的单元测试。

全部用 mock 数据 + 临时目录：不读真实 PRTS JSON、不加载 83M 图谱、不碰向量库/GPU。
覆盖：6 个知识工具 HTTP 化、对局日志（含 404/非法 id）、图谱三接口（含 404）、
证据分级（fact/retrieved/inferred）、CORS、import 不拉起 GPU/重数据栈。
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

from api.server import EpisodeStore, create_app
from knowledge.mcp_tools import schemas as S


# ------------------------------------------------------------ fakes
class FakeKnowledgeService(object):
    """与 KnowledgeService 同方法名的内存替身，返回标准 Pydantic 输出模型。"""

    def query_operator(self, name):
        if name == "能天使":
            return S.OperatorOut(
                found=True, evidence=S.EVIDENCE_FACT, name="能天使",
                display_name="能天使", star_rating=6, operator_class="狙击",
                branch="速射手", position="远程", deploy_cost="12",
                source_url="https://prts.wiki/w/能天使",
                skills=[S.SkillBrief(name="过载模式", type="攻击回复")])
        return S.OperatorOut(found=False, evidence=S.EVIDENCE_FACT,
                             message="未找到干员：%s" % name)

    def query_skill(self, operator, skill_name):
        if operator == "能天使" and "过载" in skill_name:
            return S.SkillOut(
                found=True, evidence=S.EVIDENCE_FACT, operator="能天使",
                skill=S.SkillBrief(name="过载模式", type="攻击回复",
                                   levels=[S.SkillLevel(level="10", cost="自动触发")]))
        return S.SkillOut(found=False, evidence=S.EVIDENCE_FACT,
                          message="未找到技能：%s/%s" % (operator, skill_name))

    def query_enemy(self, name, level=None):
        if name == "碎骨":
            lv = S.EnemyLevelOut(level=0, name="碎骨", position="近战",
                                 attack_type="近战", attrs={"防御力": "400"})
            return S.EnemyOut(found=True, evidence=S.EVIDENCE_FACT, name="碎骨",
                              levels=[lv], source_url="https://prts.wiki/w/碎骨")
        return S.EnemyOut(found=False, evidence=S.EVIDENCE_FACT,
                          message="未找到敌人：%s" % name)

    def query_stage(self, stage_id):
        if stage_id == "3-8":
            return S.StageOut(
                found=True, evidence=S.EVIDENCE_FACT, stage_id="3-8", title="黄昏",
                info={"部署上限": "8", "初始COST": "10"},
                enemies=[S.StageEnemyOut(name="碎骨", count="1", level="0")])
        return S.StageOut(found=False, evidence=S.EVIDENCE_FACT,
                          message="未找到关卡：%s" % stage_id)

    def search_guide(self, query, k=5, doc_type=None):
        hits = [S.GuideHit(content="能天使技能相关片段：%s" % query, score=0.91,
                           source="能天使", doc_type="operator", section="skill",
                           url="https://prts.wiki/w/能天使")]
        return S.GuideOut(found=True, query=query, embedding_backend="mock",
                          hits=hits[:k])

    def recommend_operators(self, stage_id, constraints):
        if stage_id == "3-8":
            return S.RecommendOut(
                found=True, stage_id="3-8",
                constraints_applied=constraints.model_dump() if hasattr(constraints, "model_dump") else {},
                operators=[S.RecommendedOperator(operator="艾雅法拉", operator_class="术师",
                                                 star=6, score=3.2, matched_enemies=["碎骨"])])
        return S.RecommendOut(found=False, stage_id=stage_id,
                              message="无关卡敌情，无法推荐：%s" % stage_id)


class FakeGraphProvider(object):
    def overview(self):
        return {"found": True, "evidence": "fact",
                "node_kinds": {"operator": 460, "enemy": 1816, "stage": 487, "skill": 1005},
                "edge_relations": {"COUNTERS": 1, "HAS_SKILL": 2,
                                   "CONTAINS_ENEMY": 3, "RECOMMENDS": 4},
                "total_nodes": 3768, "total_edges": 10}

    def node(self, node_id):
        if node_id == "operator:能天使":
            return {"found": True, "evidence": "fact", "node_id": node_id,
                    "attrs": {"kind": "operator", "name": "能天使", "class": "狙击"},
                    "neighbor_count": 3, "neighbors_shown": 3,
                    "neighbors_truncated": False,
                    "neighbors": [
                        {"node_id": "skill:过载模式", "relation": "HAS_SKILL",
                         "direction": "out", "kind": "skill", "name": "过载模式"}]}
        return None

    def stage_subgraph(self, stage_id):
        if stage_id == "3-8":
            return {"found": True, "evidence": "fact", "stage_id": "3-8",
                    "stage_title": "3-8 黄昏", "enemy_count": 1, "operator_count": 1,
                    "operators_truncated": False, "operator_cap": 50,
                    "nodes": [{"node_id": "stage:3-8", "kind": "stage", "name": "黄昏"},
                              {"node_id": "enemy:碎骨", "kind": "enemy", "name": "碎骨"}],
                    "edges": [{"source": "stage:3-8", "target": "enemy:碎骨",
                               "relation": "CONTAINS_ENEMY", "count": "1",
                               "evidence": "fact"}]}
        return None


# ------------------------------------------------------------ fixtures
def _sample_episode():
    return {
        "stage_id": "3-8", "outcome": "win", "backend": "mock",
        "duration_sec": 9.5,
        "reward": {
            "total": 87.0, "outcome": "win", "win_bonus": 100.0,
            "leak_penalty": -10.0, "leaked": 1, "overcost_penalty": -3.0,
            "overcost_sec": 3.0, "life_start": 3, "life_end": 2,
            "summary_line": "总分 87 = 通关+100 + 漏怪-10(1点) + 费用溢出-3(3.0s)",
            "items": [{"name": "clear", "delta": 100.0, "why": "通关奖励"}],
        },
        "steps": [
            {"step": 1, "elapsed_sec": 1.0, "cost": 15, "life": 3,
             "state_text": "当前费用15",
             "decision_summary": "部署先锋回费",
             "decision_analysis": ["费用充足，先下先锋"],
             "evidence": [{"level": "fact", "source": "PRTS"}],
             "step_reward": 0.0,
             "latency_ms": {"perceive_ms": 1.2, "knowledge_ms": 0.5,
                            "slow_ms": 12.3, "bridge_ms": 0.3,
                            "fast_ms": 0.2, "execute_ms": 0.8},
             "trace": {
                 "step": 1, "state_excerpt": "当前费用15",
                 "knowledge": {"citations": [
                     {"source": "PRTS", "evidence": "fact", "detail": "干员事实"}]},
                 "decision": {"reasoning": {"summary": "部署先锋回费"},
                              "confidence": 0.8,
                              "knowledge_used": [
                                  {"source": "PRTS", "evidence": "fact"}]},
                 "bridge": {"source": "mock"},
                 "command": {"reactor": "mock"},
                 "reflection": {"verdict": "good"},
                 "latency_ms": {"perceive_ms": 1.2, "slow_ms": 12.3}}},
            {"step": 2, "elapsed_sec": 2.0, "cost": 12, "life": 3,
             "state_text": "敌人接近", "decision_summary": "开技能",
             "decision_analysis": [],
             "evidence": [{"level": "inferred", "source": "graph"}],
             "step_reward": -1.0, "latency_ms": {"perceive_ms": 1.0},
             "trace": None},
        ],
    }


@pytest.fixture()
def client(tmp_path):
    store = EpisodeStore(str(tmp_path))
    store.save("ep-win", _sample_episode())
    app = create_app(knowledge_service=FakeKnowledgeService(),
                     graph=FakeGraphProvider(), episodes=store)
    return TestClient(app)


# ------------------------------------------------------------ import 轻量
def test_import_does_not_pull_gpu_or_heavy_stack():
    heavy = [m for m in ("torch", "transformers", "chromadb",
                         "sentence_transformers", "mcp", "ultralytics", "paddleocr")
             if m in sys.modules]
    assert heavy == []


# ------------------------------------------------------------ health / CORS
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_cors_allows_localhost_dev_origin(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


# ------------------------------------------------------------ 知识工具
def test_operator_found_and_class_alias(client):
    r = client.get("/api/operator/能天使")
    assert r.status_code == 200
    j = r.json()
    assert j["found"] is True
    assert j["evidence"] == "fact"
    assert j["class"] == "狙击"          # by_alias：operator_class -> class
    assert j["skills"][0]["name"] == "过载模式"


def test_operator_not_found_is_structured_200(client):
    r = client.get("/api/operator/不存在干员")
    assert r.status_code == 200
    j = r.json()
    assert j["found"] is False
    assert "message" in j


def test_skill_found(client):
    r = client.get("/api/skill/能天使/过载模式")
    assert r.status_code == 200
    j = r.json()
    assert j["found"] is True and j["evidence"] == "fact"
    assert j["skill"]["name"] == "过载模式"


def test_skill_not_found(client):
    r = client.get("/api/skill/能天使/不存在技能")
    assert r.json()["found"] is False


def test_enemy_found_with_level_filter(client):
    r = client.get("/api/enemy/碎骨", params={"level": 0})
    j = r.json()
    assert j["found"] is True and j["evidence"] == "fact"
    assert j["levels"][0]["attrs"]["防御力"] == "400"
    # 非法 level（负）由 FastAPI 422 拦截
    bad = client.get("/api/enemy/碎骨", params={"level": -1})
    assert bad.status_code == 422


def test_stage_found(client):
    r = client.get("/api/stage/3-8")
    j = r.json()
    assert j["found"] is True and j["title"] == "黄昏"
    assert j["info"]["部署上限"] == "8"
    assert j["enemies"][0]["name"] == "碎骨"


def test_search_retrieved_evidence(client):
    r = client.get("/api/search", params={"q": "能天使的技能是什么", "k": 5})
    j = r.json()
    assert j["found"] is True
    assert j["evidence"] == "retrieved"          # 检索结果恒为参考资料
    assert j["hits"][0]["type"] == "operator"    # by_alias：doc_type -> type
    assert j["hits"][0]["url"].startswith("https://prts.wiki/")


def test_search_requires_q(client):
    assert client.get("/api/search").status_code == 422
    assert client.get("/api/search", params={"k": 99}).status_code == 422  # k 越界


def test_search_doc_type_passthrough(client):
    r = client.get("/api/search", params={"q": "碎骨", "doc_type": "enemy"})
    assert r.status_code == 200 and r.json()["found"] is True


def test_recommend_inferred_evidence_and_constraints(client):
    r = client.get("/api/recommend/3-8",
                   params={"classes": "术师,狙击", "min_star": 5, "top_n": 8})
    j = r.json()
    assert j["found"] is True
    assert j["evidence"] == "inferred"            # 推荐恒为推断
    assert j["operators"][0]["operator"] == "艾雅法拉"
    assert j["operators"][0]["evidence"] == "inferred"
    assert "note" in j and j["note"]


def test_recommend_unknown_stage_structured(client):
    assert client.get("/api/recommend/99-9").json()["found"] is False


# ------------------------------------------------------------ 对局日志
def test_episodes_list(client):
    j = client.get("/api/episodes").json()
    assert j["found"] is True and j["count"] == 1
    meta = j["episodes"][0]
    assert meta["id"] == "ep-win" and meta["outcome"] == "win"
    assert meta["step_count"] == 2 and meta["total_reward"] == 87.0
    # 列表是轻量摘要，不含 steps 大字段
    assert "steps" not in meta


def test_episode_summary_default_no_steps(client):
    r = client.get("/api/episode/ep-win")
    assert r.status_code == 200
    j = r.json()
    assert j["found"] is True and j["outcome"] == "win"
    assert j["step_count"] == 2 and j["embedded_steps"] is False
    assert j["total_reward"] == 87.0
    assert j["reward"]["items"][0]["name"] == "clear"
    assert j["reward"]["summary_line"]
    # 默认不内嵌 steps（避免重复传输）
    assert "steps" not in j and "steps" not in j["episode"]


def test_episode_summary_embed_steps(client):
    j = client.get("/api/episode/ep-win", params={"embed_steps": "true"}).json()
    assert j["embedded_steps"] is True and len(j["steps"]) == 2
    assert j["episode"]["steps"][0]["evidence"][0] == {"level": "fact", "source": "PRTS"}


def test_episode_steps(client):
    r = client.get("/api/episode/ep-win/steps")
    j = r.json()
    assert j["step_count"] == 2
    assert j["steps"][0]["decision_summary"] == "部署先锋回费"
    assert j["steps"][1]["step_reward"] == -1.0
    # A4 evidence 统一 {level, source} 对象；A3 合流后带完整 trace
    ev0 = j["steps"][0]["evidence"]
    assert ev0 == [{"level": "fact", "source": "PRTS"}]
    trace = j["steps"][0]["trace"]
    assert trace["decision"]["reasoning"]["summary"] == "部署先锋回费"
    assert trace["reflection"]["verdict"] == "good"
    assert trace["knowledge"]["citations"][0]["evidence"] == "fact"
    assert "slow_ms" in trace["latency_ms"]
    # step 编号从 1 开始（EnvStep）
    assert j["steps"][0]["step"] == 1


def test_episode_missing_404(client):
    assert client.get("/api/episode/nope").status_code == 404
    assert client.get("/api/episode/nope/steps").status_code == 404


def test_episode_illegal_id_rejected(client, tmp_path):
    # 目录穿越/非法字符 -> 400，且不会读到目录外文件
    r = client.get("/api/episode/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)
    store = EpisodeStore(str(tmp_path))
    with pytest.raises(Exception):
        store.get("../../etc/passwd")


# ------------------------------------------------------------ 知识图谱
def test_graph_overview(client):
    j = client.get("/api/graph/overview").json()
    assert j["found"] is True
    assert j["total_nodes"] == 3768 and j["total_edges"] == 10
    assert j["node_kinds"]["operator"] == 460


def test_graph_node_detail(client):
    j = client.get("/api/graph/node/operator:能天使").json()
    assert j["found"] is True
    assert j["attrs"]["class"] == "狙击"
    assert j["neighbors"][0]["relation"] == "HAS_SKILL"
    assert client.get("/api/graph/node/operator:不存在").status_code == 404


def test_graph_stage_subgraph(client):
    j = client.get("/api/graph/subgraph/3-8").json()
    assert j["found"] is True and j["stage_title"] == "3-8 黄昏"
    rels = {e["relation"] for e in j["edges"]}
    assert "CONTAINS_ENEMY" in rels
    assert {n["node_id"] for n in j["nodes"]} >= {"stage:3-8", "enemy:碎骨"}
    assert client.get("/api/graph/subgraph/99-9").status_code == 404
