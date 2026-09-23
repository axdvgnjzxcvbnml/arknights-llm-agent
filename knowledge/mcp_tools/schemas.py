"""MCP 工具的输入/输出数据契约（Pydantic，严格校验）。

设计要点：
- 每个工具响应都带 evidence 字段，取值 "fact"（PRTS Wiki 结构化事实）或
  "inferred"（由 RAG/图谱规则推断）。COUNTERS/RECOMMENDS 类结果恒为 inferred，
  防止 LLM 把推断当事实。
- 实体不存在、查询为空等边界情况统一返回 found=False 的规范响应，不向调用方抛异常。
- 兼容 Python 3.8（统一使用 typing.Optional/List/Dict，不用内置泛型运行时注解）。
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

__all__ = [
    "EVIDENCE_FACT",
    "EVIDENCE_INFERRED",
    # 输入
    "OperatorIn",
    "SkillIn",
    "EnemyIn",
    "StageIn",
    "GuideIn",
    "RecommendConstraints",
    "RecommendIn",
    # 输出
    "SkillLevel",
    "SkillBrief",
    "TraitInfo",
    "OperatorOut",
    "SkillOut",
    "EnemyLevelOut",
    "EnemyOut",
    "StageEnemyOut",
    "StageOut",
    "GuideHit",
    "GuideOut",
    "RecommendedOperator",
    "RecommendOut",
]

EVIDENCE_FACT = "fact"
EVIDENCE_INFERRED = "inferred"
Evidence = Literal["fact", "inferred"]

# 推断结果的统一警示语，随推荐响应返回，提醒 LLM 不得当事实引用
INFERRED_NOTE = (
    "本结果由规则推断（evidence=inferred）：干员与敌人的克制关系基于防御/法术抗性/"
    "移动速度阈值与技能关键词，关卡推荐由这些克制关系聚合打分，并非 PRTS Wiki "
    "官方结论，仅供决策参考，不得作为事实陈述。"
)
PRTS_WIKI_BASE = "https://prts.wiki/w/"


# ============================ 输入模型 ============================

class OperatorIn(BaseModel):
    name: str = Field(..., description="干员页面标题/中文名，如「能天使」「阿米娅(近卫)」")


class SkillIn(BaseModel):
    operator: str = Field(..., description="干员名（页面标题），如「能天使」")
    skill_name: str = Field(..., description="技能名（支持包含匹配），如「过载模式」")


class EnemyIn(BaseModel):
    name: str = Field(..., description="敌人页面标题/中文名，如「碎骨」")
    level: Optional[int] = Field(None, description="只取指定级别（0 起）；缺省返回全部级别")


class StageIn(BaseModel):
    stage_id: str = Field(..., description="关卡编号，如「3-8」")


class GuideIn(BaseModel):
    query: str = Field(..., description="自然语言检索问题，如「能天使的技能是什么」")
    k: int = Field(5, ge=1, le=20, description="返回条数 Top-K")
    doc_type: Optional[Literal["operator", "enemy", "stage", "guide"]] = Field(
        None, description="可选类型过滤")


class RecommendConstraints(BaseModel):
    """推荐约束；全部字段可选，缺省不过滤。"""
    classes: Optional[List[str]] = Field(
        None, description="仅保留这些职业，如 [\"术师\",\"狙击\"]")
    min_star: Optional[int] = Field(None, ge=1, le=6, description="最低星级")
    max_star: Optional[int] = Field(None, ge=1, le=6, description="最高星级")
    top_n: int = Field(8, ge=1, le=30, description="返回干员数量上限")
    exclude_operators: Optional[List[str]] = Field(
        None, description="排除的干员名（如已上阵/未拥有）")


class RecommendIn(BaseModel):
    stage_id: str = Field(..., description="关卡编号，如「4-7」")
    constraints: Optional[RecommendConstraints] = Field(None, description="推荐约束")


# ============================ 输出模型 ============================

class SkillLevel(BaseModel):
    level: str = ""
    desc: str = ""
    initial: str = ""
    cost: str = ""
    duration: str = ""


class SkillBrief(BaseModel):
    name: str
    type: str = ""
    levels: List[SkillLevel] = Field(default_factory=list)


class TraitInfo(BaseModel):
    branch: str = ""
    desc: str = ""
    branch_info: str = ""


class _BaseOut(BaseModel):
    found: bool
    message: str = ""
    evidence: Evidence = EVIDENCE_FACT
    source_url: Optional[str] = None


class OperatorOut(_BaseOut):
    name: str = ""
    display_name: str = ""
    star_rating: Optional[int] = None
    operator_class: str = Field(default="", alias="class")
    branch: str = ""
    position: str = ""
    tags: List[str] = Field(default_factory=list)
    faction: str = ""
    deploy_cost: str = ""
    trait: Optional[TraitInfo] = None
    extra_attrs: Dict[str, str] = Field(default_factory=dict)
    skills: List[SkillBrief] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class SkillOut(_BaseOut):
    operator: str = ""
    skill: Optional[SkillBrief] = None


class EnemyLevelOut(BaseModel):
    level: int
    name: str = ""
    position: str = ""
    description: str = ""
    attack_type: str = ""
    movement: str = ""
    traits: List[str] = Field(default_factory=list)
    attrs: Dict[str, str] = Field(default_factory=dict)


class EnemyOut(_BaseOut):
    name: str = ""
    levels: List[EnemyLevelOut] = Field(default_factory=list)


class StageEnemyOut(BaseModel):
    name: str
    count: str = ""
    level: str = ""
    position: str = ""
    stats: Dict[str, str] = Field(default_factory=dict)


class StageOut(_BaseOut):
    stage_id: str = ""
    title: str = ""
    info: Dict[str, str] = Field(default_factory=dict)
    enemies: List[StageEnemyOut] = Field(default_factory=list)


class GuideHit(BaseModel):
    content: str
    score: float
    source: str
    doc_type: str = Field(default="", alias="type")
    section: str = ""
    url: str = ""
    evidence: Evidence = EVIDENCE_FACT  # 命中文档内容本身是 PRTS 事实

    model_config = {"populate_by_name": True}


class GuideOut(_BaseOut):
    query: str = ""
    embedding_backend: str = ""
    hits: List[GuideHit] = Field(default_factory=list)
    note: str = ("内容来自 PRTS Wiki（fact）；片段是否相关由 RAG 向量检索决定，"
                 "相关性属于工程结果而非新事实。")


class RecommendedOperator(BaseModel):
    operator: str
    operator_class: str = Field(default="", alias="class")
    star: Optional[int] = None
    score: float = 0.0
    support: int = 0
    matched_enemies: List[str] = Field(default_factory=list)
    matched_rules: List[str] = Field(default_factory=list)
    evidence: Evidence = EVIDENCE_INFERRED

    model_config = {"populate_by_name": True}


class RecommendOut(_BaseOut):
    stage_id: str = ""
    constraints_applied: Dict[str, Any] = Field(default_factory=dict)
    operators: List[RecommendedOperator] = Field(default_factory=list)
    note: str = INFERRED_NOTE
    # 推荐结果在类型层面恒为 inferred，即使构造时漏传也不会退回 fact
    evidence: Evidence = EVIDENCE_INFERRED
