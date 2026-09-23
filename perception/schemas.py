"""视觉感知结构化状态契约（Pydantic，严格校验）。

快通道（CV）各组件的输出与最终组装出的 GameState 都在此定义，作为 perception 内部
以及喂给 LLM（state_to_text）/ Agent 的统一数据边界。

来源标记（避免下游把"机器看到/估算的"当绝对事实）：
- CV 读数 source="cv"（可能误识别，带 confidence）；
- 波次推算 source="timer"，精确标注时间轴标 "timer:annotated"，均匀估算标 "timer:estimated"；
- VLM 判断 source="vlm"（inferred）。

兼容 Python 3.8（typing.Optional/List，不用内置泛型运行时注解）。
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

__all__ = [
    "Direction",
    "BBox",
    "FrameMeta",
    "DetectedObject",
    "CostStatus",
    "SkillStatus",
    "OperatorCard",
    "DeployedOperator",
    "GridCell",
    "GameMap",
    "SpawnEntry",
    "EnemyPresence",
    "GameState",
    "VLMAnalysis",
    "EvidenceRef",
]

Direction = Literal["up", "down", "left", "right"]
Terrain = Literal["ground", "highland", "blocked"]          # 地面/高台/不可部署
ReadingSource = Literal["cv", "mock", "manual"]
SpawnSource = Literal["timer:annotated", "timer:estimated", "cv", "vlm", "mock"]


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

    def width(self):
        return self.x2 - self.x1

    def height(self):
        return self.y2 - self.y1


class FrameMeta(BaseModel):
    width: int
    height: int
    channels: int = 3
    source: Literal["adb", "mock", "file"] = "mock"
    timestamp: float = 0.0


class DetectedObject(BaseModel):
    label: str
    confidence: float = 0.0
    bbox: Optional[BBox] = None
    source: ReadingSource = "cv"


class CostStatus(BaseModel):
    current: int = 0
    limit: Optional[int] = None
    confidence: float = 0.0
    source: ReadingSource = "cv"
    # ok=读数稳定可信；uncertain=相邻两帧不一致（疑似 OCR 抖动），先别据此决策；
    # missing=本帧未读到数字。
    state: Literal["ok", "uncertain", "missing"] = "ok"


class SkillStatus(BaseModel):
    operator: str = ""                 # 已部署干员名
    slot: int = 0                      # 技能槽位
    ready: bool = False                # 是否可开启
    active: bool = False               # 是否正在持续
    sp_text: str = ""                  # OCR 读到的技力文本（可能为空）
    cooldown_sec: Optional[float] = None
    confidence: float = 0.0
    source: ReadingSource = "cv"


class OperatorCard(BaseModel):
    """底部手牌中可部署的干员。"""
    name: str
    operator_class: str = ""
    cost: int = 0
    slot: int = 0
    available: bool = True             # 费用够/在轮换中可点
    elite: int = 0
    bbox: Optional[BBox] = None


class DeployedOperator(BaseModel):
    name: str
    cell_id: str = ""                  # 地图格子，如 "C3"
    direction: Direction = "up"
    hp_ratio: Optional[float] = None   # 0~1，读不到为 None


class GridCell(BaseModel):
    cell_id: str                       # "A1"：列字母 + 行号
    col: int
    row: int
    terrain: Terrain = "ground"
    deployable: bool = True
    occupied: bool = False


class GameMap(BaseModel):
    cols: int
    rows: int
    cells: List[GridCell] = Field(default_factory=list)

    def deployable_ids(self):
        # type: () -> List[str]
        return [c.cell_id for c in self.cells if c.deployable and not c.occupied]


class SpawnEntry(BaseModel):
    """波次推算：某时刻预计出场的一组敌人。"""
    enemy: str
    count: int = 1
    wave: int = 0
    expected_time_sec: float = 0.0
    appeared: bool = False             # 是否已被视觉确认出现
    confirmed_by: SpawnSource = "timer:estimated"


class EnemyPresence(BaseModel):
    """当前场上敌人（第一版主要来自计时推算，YOLO 只做出现确认）。"""
    name: str
    observed_count: int = 0
    position_hint: str = ""            # 如 "左侧"，来自地图入口/视觉
    source: SpawnSource = "timer:estimated"


class GameState(BaseModel):
    frame: Optional[FrameMeta] = None
    timestamp: float = 0.0
    stage_id: str = ""

    # 资源
    cost: Optional[CostStatus] = None
    life_points: Optional[int] = None           # 目标点耐久
    deploy_used: Optional[int] = None
    deploy_limit: Optional[int] = None

    # 干员
    operator_cards: List[OperatorCard] = Field(default_factory=list)
    deployed: List[DeployedOperator] = Field(default_factory=list)
    skills: List[SkillStatus] = Field(default_factory=list)

    # 敌人与地图
    enemies_on_field: List[EnemyPresence] = Field(default_factory=list)
    spawn_plan: List[SpawnEntry] = Field(default_factory=list)
    game_map: Optional[GameMap] = None

    # 可信度元信息
    timing_source: Literal["annotated", "estimated", "none"] = "estimated"
    notes: List[str] = Field(default_factory=list)


class EvidenceRef(BaseModel):
    """VLM 结论引用的一条来源（攻略/知识片段/视觉读数）。"""
    source: str = ""                 # 如 "PRTS攻略" / "RAG" / "CV"
    detail: str = ""                 # 如 "重装敌人弱法术"
    evidence: Literal["fact", "retrieved", "inferred"] = "retrieved"


class VLMAnalysis(BaseModel):
    """VLM 慢通道（约 2s 一次）的结构化输出：局势理解 + 战略建议 + 解释。"""
    situation: str = ""              # 局势理解（自然语言）
    strategic_advice: str = ""      # 战略建议
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence: List[EvidenceRef] = Field(default_factory=list)
    # VLM 的局势判断本身是模型推断，不是事实
    level: Literal["inferred"] = "inferred"
    analyzer: Literal["vlm", "mock"] = "vlm"
    risks: List[str] = Field(default_factory=list)   # 发现的异常/风险（可选）
    timestamp: float = 0.0
