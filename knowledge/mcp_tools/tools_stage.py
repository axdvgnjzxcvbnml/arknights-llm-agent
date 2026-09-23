"""关卡相关 MCP 工具。

- query_stage：关卡信息卡 + 本关敌情，来自 PRTS 关卡页 JSON，evidence=fact。
- recommend_operators：基于知识图谱 COUNTERS/RECOMMENDS 规则推荐，evidence=inferred，
  返回强制带推断警示 note，调用方（LLM）不得将其当作 PRTS 官方事实。
"""

from pydantic import ValidationError

from . import schemas as S
from .service import KnowledgeService, get_default_service

__all__ = ["query_stage", "recommend_operators"]


def query_stage(stage_id, service=None):
    # type: (str, KnowledgeService) -> S.StageOut
    """查询关卡信息与敌方情报。stage_id 为关卡编号，如「3-8」。"""
    S.StageIn(stage_id=stage_id if stage_id is not None else "")
    svc = service or get_default_service()
    return svc.query_stage(stage_id)


def recommend_operators(stage_id, constraints=None, service=None):
    # type: (str, dict, KnowledgeService) -> S.RecommendOut
    """按关卡敌人的类型弱点推荐干员组合（规则推断，非官方结论）。

    :param constraints: 可选 dict，键见 schemas.RecommendConstraints
        （classes / min_star / max_star / top_n / exclude_operators）。
    """
    S.StageIn(stage_id=stage_id if stage_id is not None else "")
    if constraints is None:
        cons = S.RecommendConstraints()
    elif isinstance(constraints, S.RecommendConstraints):
        cons = constraints
    elif isinstance(constraints, dict):
        try:
            cons = S.RecommendConstraints(**constraints)
        except ValidationError as exc:
            return S.RecommendOut(
                found=False, evidence=S.EVIDENCE_INFERRED,
                stage_id=str(stage_id or ""),
                message="constraints 参数不合法：%s" % exc.errors())
    else:
        return S.RecommendOut(
            found=False, evidence=S.EVIDENCE_INFERRED,
            stage_id=str(stage_id or ""),
            message="constraints 必须是 dict 或 None，收到：%s" % type(constraints).__name__)
    svc = service or get_default_service()
    return svc.recommend_operators(stage_id, cons)
