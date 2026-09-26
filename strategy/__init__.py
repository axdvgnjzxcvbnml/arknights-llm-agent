"""strategy 包：只做"决策"，不做"操作"（第十五批 任务二·3）。

与对战 decision_loop 区分：这里产出培养/资源规划建议（可读、可解释），
不下发 ADB 动作。第一版强度评估用**占位规则**，预留血狼破军强度榜（tier 数据）端口。
"""

from .operator_development import (  # noqa: F401
    OperatorProfile, StageNeed, MaterialStock, PriorityItem, DevelopmentPlan,
    OperatorDevelopmentAdvisor, load_tier_list,
    TIER_SCORE_DEFAULT, EVIDENCE_PLACEHOLDER, EVIDENCE_TIER)
