# 纯 CPU、无重依赖：Agent 的结构化输出契约（可解释性的数据边界）。
"""LLM Agent 输出 schema。

关键决策：动作部分**直接复用** action.action_space 的 Action/ActionPlan（单一事实来源），
本文件不再另造一份动作定义，保证"LLM 输出 schema"与"执行器输入"永远一致、不会漂移。

可解释性三件套都在 AgentDecision 里：
- reasoning：结构化思考过程（结论摘要 + 逐条分析 + 风险）；
- knowledge_used：本次决策引用的知识，每条带 evidence 分级
  （fact=PRTS结构化事实 / retrieved=RAG参考资料需核实 / inferred=规则或模型推断 /
   cv / estimated / mock），retrieved/inferred 绝不允许被下游当成确定事实；
- confidence：0-1 置信度。

兼容 Python 3.8（typing.Optional/List，不用内置泛型运行时注解）。
"""

import time
import uuid
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

from action.action_space import ActionPlan, PlanResult

__all__ = [
    "EvidenceLevel",
    "KnowledgeCitation",
    "KnowledgeBundle",
    "Reasoning",
    "AgentDecision",
    "BridgeState",
    "FastCommand",
    "Reflection",
    "StepRecord",
    "DecisionLog",
]

EvidenceLevel = Literal[
    "fact",        # PRTS Wiki 解析出的结构化事实
    "retrieved",   # RAG 检索到的参考资料（需核实，非事实判断）
    "inferred",    # 知识图谱规则 / 模型推断（非事实）
    "cv",          # 视觉确认
    "estimated",   # 均匀估算值
    "annotated",   # 录制/人工标注
    "mock",        # 程序合成数据
]


def _new_id(prefix):
    # type: (str) -> str
    return "%s-%s" % (prefix, uuid.uuid4().hex[:8])


class KnowledgeCitation(BaseModel):
    """一条被决策引用的知识来源。"""
    source: str = ""                       # 如 PRTS / RAG / 知识图谱 / CV
    detail: str = ""                       # 具体内容摘要
    evidence: EvidenceLevel = "retrieved"
    doc_type: str = ""                     # operator/enemy/stage/guide ...
    url: str = ""
    score: Optional[float] = None          # RAG 相似度（无则留空）


class KnowledgeBundle(BaseModel):
    """一次知识检索的产物：给 LLM 的上下文文本 + 带来源分级的引用列表。"""
    query: str = ""
    context_text: str = ""
    citations: List[KnowledgeCitation] = Field(default_factory=list)

    @classmethod
    def empty(cls, query=""):
        return cls(query=query, context_text="", citations=[])


class Reasoning(BaseModel):
    """结构化思考过程（先分析、再决策）。"""
    summary: str = ""                      # 一句话结论
    analysis: List[str] = Field(default_factory=list)   # 逐条推理依据
    considered_actions: List[str] = Field(default_factory=list)  # 候选动作及取舍
    risks: List[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    """慢思考模型的结构化输出。"""
    decision_id: str = Field(default_factory=lambda: _new_id("dec"))
    stage_id: str = ""
    elapsed_sec: float = 0.0
    reasoning: Reasoning = Field(default_factory=Reasoning)
    plan: ActionPlan = Field(default_factory=ActionPlan)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    knowledge_used: List[KnowledgeCitation] = Field(default_factory=list)
    thinker: Literal["slow-qwen3", "mock"] = "mock"
    thought_ms: float = 0.0
    created_ts: float = Field(default_factory=time.time)
    # 慢思考最后一层隐状态（latent bridge 用）。仅 V100 真实 think() 可能填充一个
    # torch.Tensor；mock / 文字桥接阶段恒为 None。
    # Any 不校验具体类型（不 import torch）；exclude=True 使其不进 model_dump/JSON，
    # 隐状态只在内存中从慢模型传到桥接层，永不落盘、不进可解释日志。
    hidden_state: Optional[Any] = Field(default=None, exclude=True)

    @property
    def actions(self):
        return self.plan.actions


class BridgeState(BaseModel):
    """慢思考隐藏态 -> 快反应输入空间的桥接表示（真实投影 TODO-V100）。"""
    decision_id: str
    vector: List[float] = Field(default_factory=list)   # mock 为确定性伪向量
    dim: int = 0
    hint: str = ""                         # mock 下用短文本承载"战略意图"
    source: Literal["projected", "mock"] = "mock"


class FastCommand(BaseModel):
    """快反应模型输出：可立即执行的操作序列。"""
    command_id: str = Field(default_factory=lambda: _new_id("cmd"))
    decision_id: str = ""
    plan: ActionPlan = Field(default_factory=ActionPlan)
    dropped: List[str] = Field(default_factory=list)     # 被快通道判定当前不可执行的动作及原因
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reactor: Literal["fast-minicpm", "mock"] = "mock"
    note: str = ""
    react_ms: float = 0.0


class Reflection(BaseModel):
    """对上一步决策的自我反思（喂给下一步慢思考）。"""
    decision_id: str
    verdict: Literal["good", "risky", "bad"] = "good"
    issues: List[str] = Field(default_factory=list)
    adjustment: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class StepRecord(BaseModel):
    """决策循环中一步的完整可解释记录。"""
    step: int
    elapsed_sec: float = 0.0
    state_excerpt: str = ""                # 喂给 LLM 的状态文本（留存便于复盘）
    knowledge: KnowledgeBundle = Field(default_factory=KnowledgeBundle)
    decision: Optional[AgentDecision] = None
    bridge: Optional[BridgeState] = None
    command: Optional[FastCommand] = None
    execute: Optional[PlanResult] = None
    reflection: Optional[Reflection] = None
    latency_ms: dict = Field(default_factory=dict)


class DecisionLog(BaseModel):
    """一次 run 的全过程日志（可解释性展示与复盘的载体）。"""
    stage_id: str = ""
    backend: str = "mock"
    steps: List[StepRecord] = Field(default_factory=list)
    started_ts: float = Field(default_factory=time.time)
    finished_ts: float = 0.0

    def total_actions(self):
        return sum((s.execute.total if s.execute else 0) for s in self.steps)

    def failed_actions(self):
        return sum((s.execute.failed if s.execute else 0) for s in self.steps)
