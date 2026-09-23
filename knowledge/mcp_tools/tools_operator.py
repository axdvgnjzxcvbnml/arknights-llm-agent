"""干员相关 MCP 工具（薄封装：参数校验 -> KnowledgeService -> Pydantic 输出）。

不 import mcp，保持为可独立单元测试的纯函数；server.py 负责注册到 MCP。
数据来源为 PRTS Wiki 解析 JSON，evidence 恒为 fact。
"""

from . import schemas as S
from .service import KnowledgeService, get_default_service

__all__ = ["query_operator", "query_skill"]


def query_operator(name, service=None):
    # type: (str, KnowledgeService) -> S.OperatorOut
    """查询干员完整信息：元数据 + 特性 + 费用等属性 + 全部技能。"""
    S.OperatorIn(name=name if name is not None else "")
    svc = service or get_default_service()
    return svc.query_operator(name)


def query_skill(operator, skill_name, service=None):
    # type: (str, str, KnowledgeService) -> S.SkillOut
    """查询某干员的指定技能详情（技能名精确优先，包含匹配兜底）。"""
    S.SkillIn(operator=operator or "", skill_name=skill_name or "")
    svc = service or get_default_service()
    return svc.query_skill(operator, skill_name)
