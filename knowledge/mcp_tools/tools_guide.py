"""攻略检索 MCP 工具：走本地 RAG（bge + ChromaDB）。

返回 evidence=retrieved：RAG 命中的是"检索到的参考文档"，不是事实判断。片段内容虽
来自 PRTS Wiki，但是否与当前问题/局势相关、可否采信需 LLM 结合上下文核实（响应 note
会明确说明），不产生新的游戏事实断言，也不得直接当作确定事实。
"""

from pydantic import ValidationError

from . import schemas as S
from .service import KnowledgeService, get_default_service

__all__ = ["search_guide"]


def search_guide(query, k=5, doc_type=None, service=None):
    # type: (str, int, str, KnowledgeService) -> S.GuideOut
    """自然语言检索攻略/知识片段，返回 Top-K，可按类型过滤。"""
    try:
        req = S.GuideIn(query=query if query is not None else "", k=k, doc_type=doc_type)
    except ValidationError as exc:
        return S.GuideOut(found=False, query=str(query or ""),
                          message="检索参数不合法：%s" % exc.errors())
    svc = service or get_default_service()
    return svc.search_guide(req.query, k=req.k, doc_type=req.doc_type)
