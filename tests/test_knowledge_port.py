"""Agent 知识端口单元测试（MCPKnowledge，D6 待办：MCP 工具与 Agent 联通）。

用 FakeKnowledgeService 模拟 6 个 MCP 工具的返回，验证 MCPKnowledge.gather()：
- 正确调用全部 6 个工具（含敌人/干员详情查询，这是 MCPKnowledge 相对旧 RAGGraphKnowledge 的新增）
- evidence 分级正确（fact/retrieved/inferred）
- 数据缺失时安全返回空
- 敌人/干员数量截断（max_enemies / max_operators）
- build_mock_loop 按 backend 自动选择知识端口
"""

from types import SimpleNamespace

import pytest

from agent.decision_loop import MockKnowledge, build_mock_loop
from agent.knowledge_port import MCPKnowledge, RAGGraphKnowledge
from agent.output_schema import KnowledgeBundle


# ---------------------------------------------------------------------------
# Fake KnowledgeService（模拟 6 个 MCP 工具返回）
# ---------------------------------------------------------------------------

class FakeGuideHit:
    def __init__(self, content, source="PRTS攻略", doc_type="guide",
                 url="https://prts.wiki/w/test", score=0.85):
        self.content = content
        self.source = source
        self.doc_type = doc_type
        self.url = url
        self.score = score


class FakeEnemyLevel:
    """模拟 EnemyLevelOut（真实 schema 用 attrs: Dict[str,str] + traits: List[str]）。"""
    def __init__(self, level=0, attrs=None, traits=None):
        self.level = level
        self.attrs = attrs or {
            "最大生命值": "200", "攻击力": "50", "防御力": "10",
            "法术抗性": "0", "攻击间隔": "1.0s", "移动速度": "慢"}
        self.traits = traits or []


class FakeEnemyOut:
    def __init__(self, name="源石虫", found=True):
        self.name = name
        self.found = found
        self.levels = [FakeEnemyLevel(level=0)] if found else []
        self.source_url = "https://prts.wiki/w/%s" % name


class FakeSkillLevel:
    def __init__(self, level="1", desc="攻击力+10%", initial="0", cost="30", duration="20s"):
        self.level = level
        self.desc = desc
        self.initial = initial
        self.cost = cost
        self.duration = duration


class FakeSkill:
    def __init__(self, name="冲锋号令", type="自动回复", levels=None):
        self.name = name
        self.type = type
        self.levels = levels or [FakeSkillLevel()]


class FakeOperatorOut:
    def __init__(self, name="翎羽", found=True):
        self.name = name
        self.found = found
        self.skills = [FakeSkill(name="冲锋号令·β型")] if found else []
        self.source_url = "https://prts.wiki/w/%s" % name


class FakeStageEnemy:
    def __init__(self, name="碎骨"):
        self.name = name


class FakeStageOut:
    def __init__(self, stage_id="3-8", found=True):
        self.stage_id = stage_id
        self.found = found
        self.enemies = [FakeStageEnemy("碎骨"), FakeStageEnemy("士兵")] if found else []
        self.source_url = "https://prts.wiki/w/%s" % stage_id


class FakeRecommendOp:
    def __init__(self, operator="阿米娅", reason="克制"):
        self.operator = operator
        self.reason = reason


class FakeRecommendOut:
    def __init__(self, found=True, operators=None):
        self.found = found
        self.operators = operators or [FakeRecommendOp("阿米娅"), FakeRecommendOp("能天使")]


class FakeGuideOut:
    def __init__(self, found=True, hits=None):
        self.found = found
        self.hits = hits or [FakeGuideHit("重装敌人弱法术，宜用术师")]


class FakeKnowledgeService:
    """模拟 KnowledgeService 的 6 个工具，记录调用次数。"""

    def __init__(self, all_found=True):
        self.all_found = all_found
        self.calls = {"search_guide": 0, "query_stage": 0, "recommend_operators": 0,
                      "query_enemy": 0, "query_operator": 0, "query_skill": 0}

    def search_guide(self, query, k=5, doc_type=None):
        self.calls["search_guide"] += 1
        return FakeGuideOut(found=self.all_found)

    def query_stage(self, stage_id):
        self.calls["query_stage"] += 1
        return FakeStageOut(stage_id=stage_id, found=self.all_found)

    def recommend_operators(self, stage_id, constraints=None):
        self.calls["recommend_operators"] += 1
        return FakeRecommendOut(found=self.all_found)

    def query_enemy(self, name, level=None):
        self.calls["query_enemy"] += 1
        return FakeEnemyOut(name=name, found=self.all_found)

    def query_operator(self, name):
        self.calls["query_operator"] += 1
        return FakeOperatorOut(name=name, found=self.all_found)

    def query_skill(self, operator, skill_name):
        self.calls["query_skill"] += 1
        return SimpleNamespace(found=self.all_found, skill=FakeSkill())


# ---------------------------------------------------------------------------
# Fake GameState（模拟 perception.schemas.GameState）
# ---------------------------------------------------------------------------

class FakeEnemyPresence:
    def __init__(self, name, observed_count=1):
        self.name = name
        self.observed_count = observed_count


class FakeOperatorCard:
    def __init__(self, name, cost=2):
        self.name = name
        self.cost = cost


def make_state(stage_id="3-8", enemies=None, operators=None):
    """构造一个最小 GameState 兼容对象。"""
    if enemies is None:
        enemies = [FakeEnemyPresence("碎骨", 3), FakeEnemyPresence("士兵", 5)]
    if operators is None:
        operators = [FakeOperatorCard("翎羽", 2), FakeOperatorCard("克洛丝", 3)]
    return SimpleNamespace(
        stage_id=stage_id,
        enemies_on_field=enemies,
        operator_cards=operators)


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

class TestMCPKnowledgeBasic:
    def test_gather_returns_knowledge_bundle(self):
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc)
        bundle = kp.gather(make_state())
        assert isinstance(bundle, KnowledgeBundle)
        assert bundle.query  # 非空 query

    def test_all_six_tools_called(self):
        """MCPKnowledge 应调用全部 6 个工具（含敌人/干员详情）。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc)
        kp.gather(make_state())
        assert svc.calls["search_guide"] == 1
        assert svc.calls["query_stage"] == 1
        assert svc.calls["recommend_operators"] == 1
        assert svc.calls["query_enemy"] >= 1  # 场上有敌人
        assert svc.calls["query_operator"] >= 1  # 有可用干员

    def test_evidence_levels_correct(self):
        """fact 来自 query_stage/query_enemy/query_operator；
        retrieved 来自 search_guide；inferred 来自 recommend_operators。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc)
        bundle = kp.gather(make_state())
        levels = {c.evidence for c in bundle.citations}
        assert "fact" in levels       # 关卡/敌人/干员
        assert "retrieved" in levels  # RAG 攻略
        assert "inferred" in levels   # 图谱推荐

    def test_fact_citations_contain_enemy_and_operator(self):
        """fact 引用应包含敌人属性和干员技能（MCPKnowledge 新增）。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc)
        bundle = kp.gather(make_state())
        fact_citations = [c for c in bundle.citations if c.evidence == "fact"]
        fact_details = [c.detail for c in fact_citations]
        # 敌人属性（detail 含"最大生命值"/"攻击力"等属性键）
        assert any("最大生命值" in d or "攻击力" in d for d in fact_details)
        # 干员技能（detail 含"[技能名]"格式，或 doc_type=operator）
        assert any("[" in d and "]" in d for d in fact_details)
        # 关卡敌情
        assert any("敌情" in d for d in fact_details)
        # doc_type 覆盖 enemy / operator / stage
        doc_types = {c.doc_type for c in fact_citations}
        assert "enemy" in doc_types
        assert "operator" in doc_types
        assert "stage" in doc_types


class TestMCPKnowledgeEdgeCases:
    def test_all_tools_not_found_safe_empty(self):
        """所有工具 found=False 时，安全返回空 citations，不抛异常。"""
        svc = FakeKnowledgeService(all_found=False)
        kp = MCPKnowledge(service=svc)
        bundle = kp.gather(make_state())
        assert bundle.citations == []
        assert bundle.context_text == ""

    def test_no_enemies_on_field(self):
        """场上无敌人时，不调用 query_enemy，但仍调用其他工具。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc)
        state = make_state(enemies=[])
        kp.gather(state)
        assert svc.calls["query_enemy"] == 0
        assert svc.calls["search_guide"] == 1  # 仍搜索攻略（用关卡名）

    def test_no_operators_available(self):
        """无可用干员时，不调用 query_operator。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc)
        state = make_state(operators=[])
        kp.gather(state)
        assert svc.calls["query_operator"] == 0

    def test_max_enemies_truncation(self):
        """敌人超过 max_enemies 时，只查前 N 个（按 observed_count 降序）。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc, max_enemies=1)
        many_enemies = [FakeEnemyPresence("A", 1), FakeEnemyPresence("B", 5),
                         FakeEnemyPresence("C", 3)]
        state = make_state(enemies=many_enemies)
        kp.gather(state)
        assert svc.calls["query_enemy"] == 1  # 只查 1 个

    def test_max_operators_truncation(self):
        """干员超过 max_operators 时，只查前 N 个（按费用升序）。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc, max_operators=1)
        many_ops = [FakeOperatorCard("贵的", 10), FakeOperatorCard("便宜的", 2)]
        state = make_state(operators=many_ops)
        kp.gather(state)
        assert svc.calls["query_operator"] == 1  # 只查 1 个（费用最低的）

    def test_no_stage_id_skips_stage_and_recommend(self):
        """无关卡 ID 时，跳过 query_stage 和 recommend_operators。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = MCPKnowledge(service=svc)
        state = make_state(stage_id="")
        kp.gather(state)
        assert svc.calls["query_stage"] == 0
        assert svc.calls["recommend_operators"] == 0
        assert svc.calls["search_guide"] == 1  # 仍搜索（用敌人名）


class TestRAGGraphKnowledgeBackwardCompat:
    def test_rag_graph_is_mcp_subclass(self):
        """RAGGraphKnowledge 是 MCPKnowledge 的子类（向后兼容）。"""
        assert issubclass(RAGGraphKnowledge, MCPKnowledge)

    def test_rag_graph_gather_works(self):
        """RAGGraphKnowledge 实例能正常 gather（行为同 MCPKnowledge）。"""
        svc = FakeKnowledgeService(all_found=True)
        kp = RAGGraphKnowledge(service=svc)
        bundle = kp.gather(make_state())
        assert isinstance(bundle, KnowledgeBundle)
        assert len(bundle.citations) > 0


class TestBuildMockLoopKnowledgeSelection:
    @staticmethod
    def _write_agent_config(tmp_path, backend, filename="agent_test.yaml"):
        """生成包含所有必需段的最小合法 agent config。"""
        import yaml
        cfg_path = tmp_path / filename
        cfg_path.write_text(yaml.dump({
            "backend": backend,
            "models": {
                "slow": {"name": "Qwen/Qwen3-8B-Thinking", "device": "cpu",
                         "dtype": "float16", "max_new_tokens": 1024,
                         "temperature": 0.7, "think_budget_ms": 4000},
                "fast": {"name": "openbmb/MiniCPM3-4B", "device": "cpu",
                         "dtype": "float16", "max_new_tokens": 256,
                         "temperature": 0.3, "react_deadline_ms": 150},
            },
            "latent_bridge": {"dim": 64, "source": "mock"},
            "knowledge": {"backend": "mock", "max_enemies": 3, "max_operators": 3},
            "loop": {"max_steps": 2, "reflect": False, "tick_interval_ms": 0,
                      "log_dir": str(tmp_path)},
            "prompt": {"system": "agent/prompt_templates/system.md",
                       "decision": "agent/prompt_templates/decision.md"},
        }), encoding="utf-8")
        return str(cfg_path)

    def test_mock_backend_uses_mock_knowledge(self, tmp_path):
        """backend=mock 时，build_mock_loop 用 MockKnowledge。"""
        cfg_path = self._write_agent_config(tmp_path, "mock")
        loop = build_mock_loop(config_path=cfg_path)
        assert isinstance(loop.knowledge, MockKnowledge)
        # 跑 2 步确认不崩
        log = loop.run(stage_id="3-8", steps=2)
        assert len(log.steps) == 2

    def test_qwen_backend_uses_mcp_knowledge(self, tmp_path):
        """backend=qwen 时，build_mock_loop 用 MCPKnowledge（真实推理应接真实知识端口）。"""
        cfg_path = self._write_agent_config(tmp_path, "qwen")
        loop = build_mock_loop(config_path=cfg_path)
        assert isinstance(loop.knowledge, MCPKnowledge)

    def test_explicit_knowledge_injection(self, tmp_path):
        """显式传入 knowledge 参数时，使用传入的实例（不按 backend 选择）。"""
        cfg_path = self._write_agent_config(tmp_path, "mock")
        fake_svc = FakeKnowledgeService(all_found=True)
        injected = MCPKnowledge(service=fake_svc)
        loop = build_mock_loop(config_path=cfg_path, knowledge=injected)
        assert loop.knowledge is injected  # 同一个对象
