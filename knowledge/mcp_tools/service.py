"""MCP 工具业务层：在 PRTS JSON / 知识图谱 / RAG 向量库之上提供 6 个查询。

分层目的：
- 本模块只依赖 pydantic 与本仓库的 rag/graph 配置；chromadb、图谱等重资源**懒加载**，
  仅在对应工具被调用时初始化，因此 import 本模块（以及 tools_*.py）不会拉起模型/向量库。
- 数据目录/图谱/向量库缺失、查询为空、实体不存在时统一返回 found=False，不向调用方抛异常。

evidence 规则：
- query_operator/query_skill/query_enemy/query_stage：解析自 PRTS Wiki -> fact
- search_guide：RAG 检索到的参考文档 -> retrieved（参考资料，非事实判断，note 说明）
- recommend_operators：来自图谱 COUNTERS/RECOMMENDS 规则 -> inferred（强制带 note）
"""

import glob
import json
import os
import urllib.parse
from typing import Dict, List, Optional, Tuple

from ..rag.config import DEFAULT_CONFIG_PATH, load_knowledge_config
from . import schemas as S

__all__ = ["KnowledgeService", "get_default_service"]

# 敌人属性中进入 attrs 的数值/机制字段（描述/地位/攻击方式等单独成列）
_ENEMY_ATTR_KEYS = (
    "最大生命值", "攻击力", "防御力", "法术抗性", "攻击半径", "重量", "移动速度",
    "攻击间隔", "生命自回速度", "元素抗性", "损伤抵抗", "异常抗性",
    "基础嘲讽等级", "目标价值",
)
_STAGE_INFO_KEYS = (
    ("desc", "关卡描述"), ("解锁条件", "解锁条件"), ("推荐等级", "推荐等级"),
    ("作战消耗", "作战消耗"), ("部署上限", "部署上限"), ("初始COST", "初始COST"),
    ("COST上限", "COST上限"), ("目标点耐久", "目标点耐久"),
    ("待处理目标", "待处理目标数量"),
)
_STAGE_ENEMY_STATS = (
    "生命值", "攻击力", "防御力", "法术抗性", "攻击间隔",
    "重量等级", "移动速度", "攻击半径",
)


def _page_url(title):
    # type: (str) -> str
    return S.PRTS_WIKI_BASE + urllib.parse.quote(title, safe="")


def _norm(text):
    # type: (object) -> str
    return (str(text).strip() if text is not None else "")


class KnowledgeService(object):
    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        # type: (str) -> None
        self.config_path = config_path
        try:
            self.config = load_knowledge_config(config_path)
            self.raw_dir = self.config["rag"]["build"]["raw_dir"]
        except Exception:
            # 配置缺失时退回默认相对路径，保证无配置环境也能安全返回 found=False
            self.config = None
            self.raw_dir = "data/prts_raw"
        self._loaded = False
        self._operators = {}          # type: Dict[str, dict]
        self._op_display = {}         # type: Dict[str, List[str]]
        self._enemies = {}            # type: Dict[str, dict]
        self._en_display = {}         # type: Dict[str, List[str]]
        self._stages_by_code = {}     # type: Dict[str, Tuple[str, dict]]
        self._graph = None
        self._retriever = None

    # -------------------------- 数据加载与实体解析 --------------------------

    def _ensure_data(self):
        # type: () -> None
        if self._loaded:
            return
        self._index_dir("operators", self._operators)
        self._index_dir("enemies", self._enemies)
        # 干员显示名 -> 页面标题
        for page, d in self._operators.items():
            display = _norm(d.get("meta", {}).get("name")) or page
            self._op_display.setdefault(display, []).append(page)
        # 敌人显示名 -> 页面标题
        for page, d in self._enemies.items():
            display = _norm(d.get("name"))
            if not display and d.get("levels"):
                display = _norm(d["levels"][-1].get("data", {}).get("名称"))
            if display:
                self._en_display.setdefault(display, []).append(page)
        # 关卡：按编号 code 索引
        for path in sorted(glob.glob(os.path.join(self.raw_dir, "stages", "*.json"))):
            page = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            code = _norm(d.get("code")) or page.split(" ")[0]
            self._stages_by_code[code] = (page, d)
        self._loaded = True

    def _index_dir(self, subdir, target):
        # type: (str, dict) -> None
        for path in sorted(glob.glob(os.path.join(self.raw_dir, subdir, "*.json"))):
            page = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    target[page] = json.load(f)
            except (OSError, ValueError):
                continue

    @staticmethod
    def _pick_basic(pages, exact):
        # type: (List[str], str) -> Optional[str]
        """显示名命中多个页面（异格/消歧义）时，优先与显示名完全相同的基础形态。"""
        if not pages:
            return None
        if exact in pages:
            return exact
        return sorted(pages, key=len)[0]

    def resolve_operator(self, name):
        # type: (str) -> Optional[str]
        self._ensure_data()
        name = _norm(name)
        if not name:
            return None
        if name in self._operators:
            return name
        return self._pick_basic(self._op_display.get(name, []), name)

    def resolve_enemy(self, name):
        # type: (str) -> Optional[str]
        self._ensure_data()
        name = _norm(name)
        if not name:
            return None
        if name in self._enemies:
            return name
        return self._pick_basic(self._en_display.get(name, []), name)

    def resolve_stage(self, stage_id):
        # type: (str) -> Optional[Tuple[str, dict]]
        self._ensure_data()
        code = _norm(stage_id)
        if not code:
            return None
        if code in self._stages_by_code:
            return self._stages_by_code[code]
        # 容错：直接传了"3-8 黄昏"或仅前缀
        for c, pair in self._stages_by_code.items():
            page = pair[0]
            if page == code or page.startswith(code + " "):
                return pair
        return None

    # -------------------------- 6 个工具 --------------------------

    def query_operator(self, name):
        # type: (str) -> S.OperatorOut
        page = self.resolve_operator(name)
        if page is None:
            return S.OperatorOut(found=False, evidence=S.EVIDENCE_FACT,
                                 message="未找到干员：%r" % _norm(name))
        d = self._operators[page]
        meta = d.get("meta", {}) or {}
        extra = d.get("extra_attrs", {}) or {}
        trait_raw = d.get("trait", {}) or {}
        trait = S.TraitInfo(
            branch=trait_raw.get("分支", ""),
            desc=trait_raw.get("描述", ""),
            branch_info=trait_raw.get("分支信息", ""),
        ) if trait_raw else None
        skills = [
            S.SkillBrief(
                name=sk.get("name", ""),
                type=sk.get("type", ""),
                levels=[S.SkillLevel(**{k: lv.get(k, "") for k in
                                        ("level", "desc", "initial", "cost", "duration")})
                        for lv in (sk.get("levels", []) or [])],
            )
            for sk in (d.get("skills", []) or [])
        ]
        tags = _norm(meta.get("tag")).split()
        return S.OperatorOut(
            found=True, evidence=S.EVIDENCE_FACT, source_url=_page_url(page),
            name=page, display_name=meta.get("name", page),
            star_rating=meta.get("star_rating"),
            operator_class=meta.get("class", ""),
            branch=meta.get("branch", ""), position=meta.get("pos", ""),
            tags=tags, faction=meta.get("group", ""),
            deploy_cost=extra.get("初始部署费用", ""),
            trait=trait, extra_attrs=dict(extra), skills=skills,
        )

    def query_skill(self, operator, skill_name):
        # type: (str, str) -> S.SkillOut
        page = self.resolve_operator(operator)
        skill_name = _norm(skill_name)
        if page is None:
            return S.SkillOut(found=False, evidence=S.EVIDENCE_FACT,
                              message="未找到干员：%r" % _norm(operator))
        if not skill_name:
            return S.SkillOut(found=False, evidence=S.EVIDENCE_FACT,
                              message="skill_name 不能为空",
                              operator=page)
        skills = self._operators[page].get("skills", []) or []
        target = None
        # 精确名优先，再退化为双向包含匹配
        for sk in skills:
            if sk.get("name") == skill_name:
                target = sk
                break
        if target is None:
            for sk in skills:
                sname = sk.get("name", "")
                if sname and (skill_name in sname or sname in skill_name):
                    target = sk
                    break
        if target is None:
            names = [sk.get("name", "") for sk in skills]
            return S.SkillOut(
                found=False, operator=page, evidence=S.EVIDENCE_FACT,
                source_url=_page_url(page),
                message="干员「%s」没有匹配 %r 的技能；现有技能：%s"
                        % (page, skill_name, "、".join(names) if names else "（无）"))
        brief = S.SkillBrief(
            name=target.get("name", ""), type=target.get("type", ""),
            levels=[S.SkillLevel(**{k: lv.get(k, "") for k in
                                    ("level", "desc", "initial", "cost", "duration")})
                    for lv in (target.get("levels", []) or [])],
        )
        return S.SkillOut(found=True, operator=page, skill=brief,
                          evidence=S.EVIDENCE_FACT, source_url=_page_url(page))

    def query_enemy(self, name, level=None):
        # type: (str, Optional[int]) -> S.EnemyOut
        page = self.resolve_enemy(name)
        if page is None:
            return S.EnemyOut(found=False, evidence=S.EVIDENCE_FACT,
                              message="未找到敌人：%r" % _norm(name))
        d = self._enemies[page]
        levels_out = []
        for lv in d.get("levels", []) or []:
            data = lv.get("data", {}) or {}
            if level is not None and int(lv.get("level", -1)) != level:
                continue
            traits = data.get("特性") or []
            if not isinstance(traits, (list, tuple)):
                traits = [str(traits)] if traits else []
            attrs = {k: str(data[k]) for k in _ENEMY_ATTR_KEYS if data.get(k) not in (None, "")}
            levels_out.append(S.EnemyLevelOut(
                level=int(lv.get("level", 0)),
                name=data.get("名称", page), position=data.get("地位", ""),
                description=data.get("描述", ""), attack_type=data.get("攻击方式", ""),
                movement=data.get("行动方式", ""),
                traits=[str(t) for t in traits if t], attrs=attrs,
            ))
        if level is not None and not levels_out:
            have = [int(lv.get("level", 0)) for lv in d.get("levels", []) or []]
            return S.EnemyOut(found=False, name=page, evidence=S.EVIDENCE_FACT,
                              source_url=_page_url(page),
                              message="敌人「%s」没有级别 %d；现有级别：%s"
                                      % (page, level, have))
        return S.EnemyOut(found=True, name=page, levels=levels_out,
                          evidence=S.EVIDENCE_FACT, source_url=_page_url(page))

    def query_stage(self, stage_id):
        # type: (str) -> S.StageOut
        pair = self.resolve_stage(stage_id)
        if pair is None:
            return S.StageOut(found=False, evidence=S.EVIDENCE_FACT,
                              message="未找到关卡：%r" % _norm(stage_id))
        page, d = pair
        code = _norm(d.get("code")) or page.split(" ")[0]
        normal = d.get("normal", {}) or {}
        info = {}
        for src_key, label in _STAGE_INFO_KEYS:
            val = normal.get(src_key)
            if val not in (None, ""):
                info[label] = str(val)
        enemies = []
        for row in d.get("enemies", []) or []:
            stats = {label: str(row[k]) for k, label in
                     (("生命值", "生命值"), ("攻击力", "攻击力"), ("防御力", "防御力"),
                      ("法术抗性", "法术抗性"), ("攻击间隔", "攻击间隔"),
                      ("重量等级", "重量等级"), ("移动速度", "移动速度"))
                     if row.get(k) not in (None, "")}
            enemies.append(S.StageEnemyOut(
                name=row.get("名称", ""), count=str(row.get("数量", "")),
                level=str(row.get("级别", "")), position=row.get("地位", ""),
                stats=stats,
            ))
        return S.StageOut(found=True, stage_id=code, title=page, info=info,
                          enemies=enemies, evidence=S.EVIDENCE_FACT,
                          source_url=_page_url(page))

    def search_guide(self, query, k=5, doc_type=None):
        # type: (str, int, Optional[str]) -> S.GuideOut
        query = _norm(query)
        if not query:
            return S.GuideOut(found=False, query="", message="query 不能为空")
        try:
            retriever = self._get_retriever()
            rows = retriever.search(query, k=k, doc_type=doc_type)
        except Exception as exc:  # 向量库/模型缺失等：友好返回而非堆栈
            return S.GuideOut(found=False, query=query,
                             message="RAG 检索不可用：%s（请先构建向量库）" % exc)
        hits = []
        for r in rows:
            m = r.get("metadata", {}) or {}
            hits.append(S.GuideHit(
                content=r.get("content", ""), score=float(r.get("score", 0.0)),
                source=m.get("source", ""), doc_type=m.get("type", ""),
                section=m.get("section", ""), url=m.get("url", ""),
            ))
        return S.GuideOut(
            found=bool(hits), query=query, hits=hits,
            embedding_backend=getattr(retriever.embedder, "backend", ""),
            message="" if hits else "未检索到相关文档",
        )

    def recommend_operators(self, stage_id, constraints=None):
        # type: (str, Optional[S.RecommendConstraints]) -> S.RecommendOut
        cons = constraints or S.RecommendConstraints()
        pair = self.resolve_stage(stage_id)
        if pair is None:
            return S.RecommendOut(found=False, evidence=S.EVIDENCE_INFERRED,
                                  stage_id=_norm(stage_id),
                                  message="未找到关卡：%r" % _norm(stage_id))
        code = _norm(pair[1].get("code")) or pair[0].split(" ")[0]
        try:
            graph = self._get_graph()
            rows = graph.operators_for_stage(code)
        except Exception as exc:
            return S.RecommendOut(found=False, evidence=S.EVIDENCE_INFERRED,
                                  stage_id=code,
                                  message="知识图谱不可用：%s（请先构建图谱）" % exc)

        class_allow = set(cons.classes or [])
        excluded = set(cons.exclude_operators or [])
        picked = []
        for r in rows:
            name = r.get("operator", "")
            star = r.get("star")
            star = None if star in (None, -1, "-1") else int(star)
            if class_allow and r.get("class", "") not in class_allow:
                continue
            if cons.min_star is not None and (star is None or star < cons.min_star):
                continue
            if cons.max_star is not None and (star is None or star > cons.max_star):
                continue
            if name in excluded:
                continue
            picked.append(S.RecommendedOperator(
                operator=name, operator_class=r.get("class", ""), star=star,
                score=float(r.get("score", 0.0)), support=int(r.get("support", 0)),
                matched_enemies=[x for x in str(r.get("matched_enemies", "")).split("、") if x],
                matched_rules=[x for x in str(r.get("matched_rules", "")).split("、") if x],
            ))
            if len(picked) >= cons.top_n:
                break

        applied = cons.model_dump(exclude_none=True)
        if not picked:
            return S.RecommendOut(
                found=True, evidence=S.EVIDENCE_INFERRED, stage_id=code,
                constraints_applied=applied, operators=[],
                message="本关敌人未触发任何克制规则（防/抗/速未达阈值），"
                        "规则层面没有可推荐的针对性干员；可按通用阵容配队。")
        return S.RecommendOut(found=True, evidence=S.EVIDENCE_INFERRED,
                              stage_id=code, constraints_applied=applied,
                              operators=picked)

    # -------------------------- 重资源懒加载 --------------------------

    def _get_retriever(self):
        if self._retriever is None:
            from ..rag.retriever import Retriever  # 延迟：import 即可能拉起 chromadb
            self._retriever = Retriever(
                config=self.config) if self.config else Retriever()
        return self._retriever

    def _get_graph(self):
        if self._graph is None:
            from ..graph.query_graph import GraphQuery  # 延迟：依赖 networkx/GraphML
            self._graph = GraphQuery(config=self.config) if self.config else GraphQuery()
        return self._graph


_DEFAULT_SERVICE = None


def get_default_service():
    # type: () -> KnowledgeService
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = KnowledgeService()
    return _DEFAULT_SERVICE
