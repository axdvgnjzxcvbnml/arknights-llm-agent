"""MCP 工具子包。

既可经 server.py 以 MCP 协议暴露给 LLM，也可在进程内直接调用工具函数
（agent 决策循环走进程内调用，省去 JSON-RPC 开销）。
"""

from .service import KnowledgeService, get_default_service
from .tools_enemy import query_enemy
from .tools_guide import search_guide
from .tools_operator import query_operator, query_skill
from .tools_stage import query_stage, recommend_operators

__all__ = [
    "KnowledgeService",
    "get_default_service",
    "query_operator",
    "query_skill",
    "query_enemy",
    "query_stage",
    "search_guide",
    "recommend_operators",
]
