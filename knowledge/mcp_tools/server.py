"""arknights-llm-agent 的 MCP 服务端（FastMCP / stdio）。

向 LLM Agent 暴露 6 个知识工具：
- query_operator(name)                 干员完整信息（fact）
- query_skill(operator, skill_name)    技能详情（fact）
- query_enemy(name, level?)            敌人分级属性（fact）
- query_stage(stage_id)                关卡信息+敌情（fact）
- search_guide(query, k?, doc_type?)   RAG 检索参考资料（evidence=retrieved，非事实判断）
- recommend_operators(stage_id, constraints?)  关卡干员推荐（inferred，非官方事实）

启动：
    python -m knowledge.mcp_tools.server          # stdio，供 MCP 客户端接入
客户端配置：command=python, args=["-m","knowledge.mcp_tools.server"]

注意：
- 推荐类结果 evidence=inferred 且带警示 note，Agent 不得当作 PRTS 官方事实；
- search_guide 结果 evidence=retrieved，是参考资料而非确定事实，需结合上下文核实。
# TODO-V100: 本服务不依赖 GPU；V100 环境下 RAG 检索更快（embedding device=cuda）。
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import schemas as S
from . import tools_enemy, tools_guide, tools_operator, tools_stage

mcp = FastMCP("arknights-prts-knowledge")


def _dump(model):
    # type: (object) -> dict
    return model.model_dump(by_alias=True)


@mcp.tool()
def query_operator(name: str) -> dict:
    """查询明日方舟干员完整信息：职业/星级/分支/标签/势力/特性/部署费用与全部技能。

    Args:
        name: 干员中文名（页面标题），如「能天使」「阿米娅(近卫)」。
    """
    try:
        return _dump(tools_operator.query_operator(name))
    except Exception as exc:  # 通道兜底：任何意外都返回结构化失败而非抛异常
        return {"found": False, "evidence": S.EVIDENCE_FACT,
                "message": "query_operator 失败：%s" % exc}


@mcp.tool()
def query_skill(operator: str, skill_name: str) -> dict:
    """查询某干员单个技能的详情（机制类型与各等级效果/技力/持续）。

    Args:
        operator: 干员名，如「能天使」。
        skill_name: 技能名，精确优先、包含匹配兜底，如「过载模式」。
    """
    try:
        return _dump(tools_operator.query_skill(operator, skill_name))
    except Exception as exc:
        return {"found": False, "evidence": S.EVIDENCE_FACT,
                "message": "query_skill 失败：%s" % exc}


@mcp.tool()
def query_enemy(name: str, level: Optional[int] = None) -> dict:
    """查询敌人属性，按级别返回地位/攻击方式/生命/攻防/法抗/特性等。

    Args:
        name: 敌人中文名，如「碎骨」。
        level: 可选，指定级别（从 0 起）；省略则返回全部级别。
    """
    try:
        return _dump(tools_enemy.query_enemy(name, level=level))
    except Exception as exc:
        return {"found": False, "evidence": S.EVIDENCE_FACT,
                "message": "query_enemy 失败：%s" % exc}


@mcp.tool()
def query_stage(stage_id: str) -> dict:
    """查询关卡信息卡（部署上限/初始COST/耐久等）与本关出场敌人及数量、级别、数值。

    Args:
        stage_id: 关卡编号，如「3-8」。
    """
    try:
        return _dump(tools_stage.query_stage(stage_id))
    except Exception as exc:
        return {"found": False, "evidence": S.EVIDENCE_FACT,
                "message": "query_stage 失败：%s" % exc}


@mcp.tool()
def search_guide(query: str, k: int = 5, doc_type: Optional[str] = None) -> dict:
    """用 RAG 在 PRTS 知识片段中做语义检索，返回 Top-K 片段及来源 URL。

    返回 evidence=retrieved：这是检索到的"参考资料"，不是事实判断；片段是否相关、
    可否采信需结合当前上下文核实，不要直接当作确定事实陈述。

    Args:
        query: 自然语言问题，如「能天使的技能是什么」。
        k: 返回条数，1-20，默认 5。
        doc_type: 可选类型过滤：operator / enemy / stage / guide。
    """
    try:
        return _dump(tools_guide.search_guide(query, k=k, doc_type=doc_type))
    except Exception as exc:
        return {"found": False, "evidence": S.EVIDENCE_RETRIEVED,
                "message": "search_guide 失败：%s" % exc}


@mcp.tool()
def recommend_operators(stage_id: str, constraints: Optional[dict] = None) -> dict:
    """根据关卡敌人的类型弱点，经知识图谱规则推断推荐干员组合。

    结果 evidence=inferred（非 PRTS 官方结论），含命中的敌人/规则与打分，仅供参考。

    Args:
        stage_id: 关卡编号，如「4-7」。
        constraints: 可选约束，键：classes(职业白名单)、min_star、max_star、
            top_n(默认8)、exclude_operators(排除名单)。
    """
    try:
        return _dump(tools_stage.recommend_operators(stage_id, constraints=constraints))
    except Exception as exc:
        return {"found": False, "evidence": S.EVIDENCE_INFERRED,
                "message": "recommend_operators 失败：%s" % exc}


def main():
    mcp.run()  # 默认 stdio 传输


if __name__ == "__main__":
    main()
