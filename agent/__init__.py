"""agent 包：LLM Agent 核心（慢思考 / 快反应 / 桥接 / 决策循环 / Prompt / 输出契约）。

导入本包只装配 pydantic/yaml 级别的契约与编排；torch/transformers 等 GPU 依赖在
slow/fast/bridge 的真实模型方法内延迟导入，perception 等仅在 build_mock_loop() 内导入，
因此 `import agent` 本身不拉起 GPU/numpy 栈。
"""

from .config import DEFAULT_CONFIG_PATH, load_agent_config
from .output_schema import (AgentDecision, BridgeState, DecisionLog, FastCommand,
                            KnowledgeBundle, KnowledgeCitation, Reasoning,
                            Reflection, StepRecord)
from .slow_thinker import (BaseSlowThinker, MockSlowThinker, SlowThinkerQwen3,
                           load_template, render_template)
from .fast_reactor import BaseFastReactor, FastReactorMiniCPM, MockFastReactor
from .latent_bridge import (BaseLatentBridge, LatentBridgeProjector, MockLatentBridge)
from .decision_loop import (BaseKnowledge, BasePerception, DecisionLoop,
                            MockKnowledge, MockPerception, RAGGraphKnowledge,
                            build_mock_loop, render_decision_log,
                            write_decision_log)

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "load_agent_config",
    # 契约
    "Reasoning", "KnowledgeCitation", "KnowledgeBundle", "AgentDecision",
    "BridgeState", "FastCommand", "Reflection", "StepRecord", "DecisionLog",
    # 慢思考
    "BaseSlowThinker", "SlowThinkerQwen3", "MockSlowThinker",
    "load_template", "render_template",
    # 快反应 / 桥接
    "BaseFastReactor", "FastReactorMiniCPM", "MockFastReactor",
    "BaseLatentBridge", "LatentBridgeProjector", "MockLatentBridge",
    # 循环 / 端口 / 装配 / 日志
    "DecisionLoop", "BasePerception", "MockPerception",
    "BaseKnowledge", "MockKnowledge", "RAGGraphKnowledge",
    "build_mock_loop", "render_decision_log", "write_decision_log",
]
