"""HTTP API 层（FastAPI）。

把知识库 MCP 工具、对局日志、知识图谱查询封装成 HTTP 接口，供前端/可视化调用。
本包不依赖 GPU；导入 `api.server` 不会拉起 torch / chromadb / bge（图谱与 RAG 均懒加载）。

- MCP 工具 HTTP 化：见 ``api.server`` 中 ``/api/operator`` 等路由，直接复用
  ``knowledge.mcp_tools.tools_*`` 纯函数（不 import FastMCP 的 ``server.py``）。
- 依赖注入：``create_app(...)`` 允许注入 knowledge service / graph provider / episode store，
  单元测试用 mock 数据即可跑通全部接口，不读真实 PRTS 数据、不加载 83M 图谱。
"""

from .server import (
    EpisodeStore,
    GraphUnavailable,
    NetworkXGraphProvider,
    create_app,
)

__all__ = [
    "EpisodeStore",
    "GraphUnavailable",
    "NetworkXGraphProvider",
    "create_app",
]
