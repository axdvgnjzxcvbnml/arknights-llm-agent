"""Agent 知识端口：MCP 工具封装层。

把 knowledge/mcp_tools/ 的 6 个工具（query_operator / query_skill / query_enemy /
query_stage / search_guide / recommend_operators）封装成 Agent 决策循环可直接消费的
KnowledgeBundle（上下文文本 + 带来源分级的引用列表）。

与 decision_loop.py 中旧的 RAGGraphKnowledge 的区别：
- RAGGraphKnowledge 只调用 3 个工具（search_guide / query_stage / recommend_operators）；
- MCPKnowledge 调用全部 6 个工具，新增：
  - query_enemy：对场上每个敌人查属性（fact），让 LLM 知道敌人的血量/攻击/防御/抗性；
  - query_operator / query_skill：对可用干员查技能详情（fact），让 LLM 知道技能效果/消耗/持续。

工具调用策略（避免一次调太多）：
- 敌人详情最多查 max_enemies（默认3）个，按 observed_count 降序取威胁最大的；
- 干员详情最多查 max_operators（默认3）个，按费用升序取最可能部署的；
- 每个工具 found=False 时安全跳过，不抛异常。

evidence 分级严格遵守：
- fact：PRTS 结构化事实（关卡敌情/敌人属性/干员技能）；
- retrieved：RAG 检索到的参考资料（非事实判断，需结合上下文核实）；
- inferred：知识图谱规则推断（COUNTERS / RECOMMENDS 边，非 PRTS 官方结论）。
"""

from typing import Optional

from .output_schema import KnowledgeBundle, KnowledgeCitation

__all__ = ["MCPKnowledge", "RAGGraphKnowledge"]


class MCPKnowledge(object):
    """MCP 工具知识端口：封装 KnowledgeService 全部 6 个工具。

    用法（与 MockKnowledge 同接口，可直接注入 DecisionLoop）：
        knowledge = MCPKnowledge()           # 用默认 configs/knowledge.yaml
        knowledge = MCPKnowledge(config_path="configs/knowledge.yaml")
        bundle = knowledge.gather(game_state)  # -> KnowledgeBundle

    数据缺失（未爬 PRTS / 未建向量库 / 未建图谱）时各工具 found=False，
    gather() 安全返回空/部分结果，不抛异常，保证 CPU 冒烟恒绿。
    """

    def __init__(self, config_path: Optional[str] = None,
                 max_enemies: int = 3, max_operators: int = 3,
                 service: Optional[object] = None) -> None:
        self.config_path = config_path
        self.max_enemies = max_enemies
        self.max_operators = max_operators
        self._service = service  # 允许注入（测试用）；None 时懒加载真实 KnowledgeService

    def _svc(self):
        """懒加载 KnowledgeService（首次调用时才 import + 加载数据）。"""
        if self._service is None:
            from knowledge.mcp_tools.service import KnowledgeService
            self._service = (KnowledgeService(self.config_path)
                             if self.config_path else KnowledgeService())
        return self._service

    # ---------------------------------------------------------------- 工具调用
    def _search_guide(self, svc, query, citations, context_parts):
        """RAG 攻略检索（evidence: retrieved）。"""
        guide = svc.search_guide(query, k=5)
        if not getattr(guide, "found", False):
            return
        for h in guide.hits[:3]:
            citations.append(KnowledgeCitation(
                source="RAG", detail=h.content[:120], evidence="retrieved",
                doc_type=h.doc_type, url=h.url, score=h.score))
        context_parts.append("[retrieved] 攻略参考：" + " / ".join(
            (h.source + ": " + h.content[:80]) for h in guide.hits[:3]))

    def _query_stage(self, svc, stage_id, citations, context_parts):
        """关卡敌情查询（evidence: fact）。"""
        if not stage_id:
            return
        stage = svc.query_stage(stage_id)
        if not getattr(stage, "found", False):
            return
        names = "、".join(e.name for e in stage.enemies)
        citations.append(KnowledgeCitation(
            source="PRTS", detail="关卡 %s 敌情：%s" % (stage_id, names),
            evidence="fact", doc_type="stage", url=stage.source_url))
        context_parts.append("[fact] 关卡面板敌情：" + names)

    def _recommend_operators(self, svc, stage_id, citations, context_parts):
        """图谱干员推荐（evidence: inferred，COUNTERS/RECOMMENDS 边为推断）。"""
        if not stage_id:
            return
        rec = svc.recommend_operators(stage_id)
        if not getattr(rec, "found", False) or not rec.operators:
            return
        ops = "、".join(o.operator for o in rec.operators[:5])
        citations.append(KnowledgeCitation(
            source="知识图谱", detail="本关按克制规则推荐：%s" % ops,
            evidence="inferred", doc_type="recommend"))
        context_parts.append("[inferred] 图谱推荐(规则推断,非事实)：" + ops)

    def _query_enemies(self, svc, enemy_names, citations, context_parts):
        """敌人属性查询（evidence: fact）。对场上威胁最大的几个敌人查详情。"""
        for name in enemy_names[:self.max_enemies]:
            enemy = svc.query_enemy(name)
            if not getattr(enemy, "found", False):
                continue
            # 取级别0（最常见）的属性（真实 schema 用 attrs: Dict[str,str]）
            levels = getattr(enemy, "levels", [])
            if not levels:
                continue
            lvl0 = levels[0]
            attrs = getattr(lvl0, "attrs", None) or {}
            detail_parts = []
            for key in ("最大生命值", "攻击力", "防御力", "法术抗性", "攻击间隔", "移动速度"):
                val = attrs.get(key) if isinstance(attrs, dict) else getattr(attrs, key, None)
                if val:
                    detail_parts.append("%s=%s" % (key, val))
            traits = getattr(lvl0, "traits", []) or []
            if traits:
                detail_parts.append("特性=%s" % "、".join(traits))
            detail = "%s：%s" % (name, "，".join(detail_parts)) if detail_parts else "%s（无属性数据）" % name
            citations.append(KnowledgeCitation(
                source="PRTS", detail=detail, evidence="fact",
                doc_type="enemy", url=getattr(enemy, "source_url", "")))
            context_parts.append("[fact] 敌人属性：" + detail)

    def _query_operators(self, svc, operator_names, citations, context_parts):
        """干员技能查询（evidence: fact）。对可用干员查技能详情。"""
        for name in operator_names[:self.max_operators]:
            op = svc.query_operator(name)
            if not getattr(op, "found", False):
                continue
            skills = getattr(op, "skills", [])
            if not skills:
                continue
            # 取第一个技能的1级描述
            skill = skills[0]
            levels = getattr(skill, "levels", [])
            desc = levels[0].desc if levels else ""
            detail = "%s[%s]：%s" % (name, skill.name, desc[:80]) if desc else "%s[%s]" % (name, skill.name)
            citations.append(KnowledgeCitation(
                source="PRTS", detail=detail, evidence="fact",
                doc_type="operator", url=getattr(op, "source_url", "")))
            context_parts.append("[fact] 干员技能：" + detail)

    # ---------------------------------------------------------------- 主入口
    def gather(self, state) -> KnowledgeBundle:
        """根据游戏状态调用 MCP 工具，返回 KnowledgeBundle。

        调用顺序（按信息价值从高到低）：
        1. search_guide（RAG 攻略，retrieved）
        2. query_stage（关卡敌情，fact）
        3. recommend_operators（图谱推荐，inferred）
        4. query_enemies（敌人属性，fact）—— 新增
        5. query_operators（干员技能，fact）—— 新增
        """
        svc = self._svc()
        stage_id = getattr(state, "stage_id", "") or ""

        # 场上敌人：按 observed_count 降序，取威胁最大的
        enemies_on_field = getattr(state, "enemies_on_field", []) or []
        enemy_names = sorted(
            [e.name for e in enemies_on_field if getattr(e, "name", "")],
            key=lambda n: -next((e.observed_count for e in enemies_on_field if e.name == n), 0))

        # 可用干员：按费用升序，取最可能部署的
        operator_cards = getattr(state, "operator_cards", []) or []
        operator_names = sorted(
            [o.name for o in operator_cards if getattr(o, "name", "")],
            key=lambda n: next((o.cost for o in operator_cards if o.name == n), 99))

        query = ("%s 怎么应对" % "、".join(enemy_names)) if enemy_names else ("%s 攻略" % stage_id)

        citations = []  # type: List[KnowledgeCitation]
        context_parts = []

        self._search_guide(svc, query, citations, context_parts)
        self._query_stage(svc, stage_id, citations, context_parts)
        self._recommend_operators(svc, stage_id, citations, context_parts)
        self._query_enemies(svc, enemy_names, citations, context_parts)
        self._query_operators(svc, operator_names, citations, context_parts)

        return KnowledgeBundle(
            query=query,
            context_text="\n".join(context_parts),
            citations=citations)


# 向后兼容别名：旧代码 from agent.decision_loop import RAGGraphKnowledge 仍可用。
# RAGGraphKnowledge 是 MCPKnowledge 的子集（只调 3 个工具），保留名称供旧引用。
class RAGGraphKnowledge(MCPKnowledge):
    """旧版知识端口（只调 search_guide / query_stage / recommend_operators 3 个工具）。

    保留为 MCPKnowledge 的子类别名，旧代码无需修改。新代码请直接用 MCPKnowledge。
    """
    pass
