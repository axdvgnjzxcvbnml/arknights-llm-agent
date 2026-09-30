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
    """VLM 结论引用的一条来源（攻略/知识片段/视觉读数）。

    evidence 8 档全集（前后端统一，见 docs/api-contract.md）：
    - fact: 确定事实（账号/关卡实测、游戏规则、PRTS数值）
    - cv: CV 快通道确认（视觉检测结果）
    - retrieved: 检索到的外部资料（RAG/攻略/强度榜观点），非事实判定
    - inferred: 规则/模型推断（克制规则推导、VLM局势判断）
    - estimated: 估算值（均匀出怪时间轴、短期窗口、源石估算）
    - vlm: VLM 慢通道观点（模型输出，非事实）
    - annotated: 人工标注时间轴/数据（私服验证、人工校准）
    - mock: mock 数据（CPU侧闭环验证用）
    """
    source: str = ""                 # 如 "PRTS攻略" / "RAG" / "CV"
    detail: str = ""                 # 如 "重装敌人弱法术"
    evidence: Literal["fact", "cv", "retrieved", "inferred", "estimated", "vlm", "annotated", "mock"] = "retrieved"


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


# ============================================================================
# Stage 2 双通道状态表示（文本通道 + 张量通道）
# 文本通道：给 LLM，保持 state_to_text 输出
# 张量通道：给搜索/CNN/规划层，结构化数值张量
# ============================================================================

# 张量维度常量（固定尺寸，不足 padding，超出裁剪）
MAP_H = 10          # 地图行数
MAP_W = 10          # 地图列数
MAP_C = 4           # 地图通道数：可部署/已占用/地面/高台
MAX_ENEMIES = 20    # 最大同时在场敌人数
ENEMY_F = 6         # 敌人特征数：col/row/hp_ratio/speed/type_id/count
MAX_OPERATORS = 12  # 最大可用干员数（手牌）
OPERATOR_F = 6      # 干员特征数：cost/range_id/cooldown/class_id/available/elite
MAX_DEPLOYED = 8    # 最大已部署干员数
DEPLOYED_F = 5      # 已部署特征：col/row/direction_id/hp_ratio/class_id


class MapTensor(BaseModel):
    """地图张量：H×W×C，C=4（可部署/已占用/地面/高台）。"""
    shape: List[int] = Field(default_factory=lambda: [MAP_H, MAP_W, MAP_C])
    # 扁平化存储，按行优先：data[h*W*C + w*C + c]
    data: List[float] = Field(default_factory=list)

    def channel(self, c: int) -> List[List[float]]:
        """取出第 c 通道，返回 H×W 二维列表。"""
        return [
            [self.data[h * MAP_W * MAP_C + w * MAP_C + c] for w in range(MAP_W)]
            for h in range(MAP_H)
        ]


class EnemyTensor(BaseModel):
    """敌人张量：K×F，K=MAX_ENEMIES，不足零填充。"""
    shape: List[int] = Field(default_factory=lambda: [MAX_ENEMIES, ENEMY_F])
    data: List[float] = Field(default_factory=list)
    valid_count: int = 0  # 实际有效敌人数（非 padding）

    def enemy(self, k: int) -> List[float]:
        """取出第 k 个敌人的特征向量。"""
        return self.data[k * ENEMY_F:(k + 1) * ENEMY_F]


class OperatorTensor(BaseModel):
    """可用干员张量：P×F，P=MAX_OPERATORS，不足零填充。"""
    shape: List[int] = Field(default_factory=lambda: [MAX_OPERATORS, OPERATOR_F])
    data: List[float] = Field(default_factory=list)
    valid_count: int = 0

    def operator(self, p: int) -> List[float]:
        return self.data[p * OPERATOR_F:(p + 1) * OPERATOR_F]


class DeployedTensor(BaseModel):
    """已部署干员张量：D×F，D=MAX_DEPLOYED。"""
    shape: List[int] = Field(default_factory=lambda: [MAX_DEPLOYED, DEPLOYED_F])
    data: List[float] = Field(default_factory=list)
    valid_count: int = 0


class ScalarState(BaseModel):
    """全局标量状态。"""
    cost: float = 0.0
    life_points: float = 0.0
    deploy_used: float = 0.0
    deploy_limit: float = 0.0
    timestamp: float = 0.0
    # 费用读数状态：0=ok, 1=uncertain, 2=missing
    cost_state: int = 0


class StateTensor(BaseModel):
    """
    双通道状态表示的张量通道。

    与文本通道（state_to_text 输出）对应同一 GameState，信息对齐：
    - 文本通道给 LLM 做推理
    - 张量通道给搜索/CNN/规划层做数值计算

    所有张量固定尺寸，不足零填充，超出裁剪，便于批量处理。
    """
    stage_id: str = ""
    map_tensor: MapTensor = Field(default_factory=MapTensor)
    enemy_tensor: EnemyTensor = Field(default_factory=EnemyTensor)
    operator_tensor: OperatorTensor = Field(default_factory=OperatorTensor)
    deployed_tensor: DeployedTensor = Field(default_factory=DeployedTensor)
    scalars: ScalarState = Field(default_factory=ScalarState)
    # 张量通道的来源标注（与文本通道一致）
    timing_source: Literal["annotated", "estimated", "none"] = "estimated"
    notes: List[str] = Field(default_factory=list)


# ============================================================================
# 形式化动作空间（可枚举）
# ============================================================================

ActionType = Literal["deploy", "skill", "retreat", "wait"]


class DeployAction(BaseModel):
    """部署动作：干员索引 + 格子坐标 + 朝向。"""
    type: Literal["deploy"] = "deploy"
    operator_idx: int = Field(..., ge=0, lt=MAX_OPERATORS)
    grid_col: int = Field(..., ge=0, lt=MAP_W)
    grid_row: int = Field(..., ge=0, lt=MAP_H)
    direction: Direction = "up"


class SkillAction(BaseModel):
    """技能动作：已部署干员索引。"""
    type: Literal["skill"] = "skill"
    deployed_idx: int = Field(..., ge=0, lt=MAX_DEPLOYED)


class RetreatAction(BaseModel):
    """撤退动作：已部署干员索引。"""
    type: Literal["retreat"] = "retreat"
    deployed_idx: int = Field(..., ge=0, lt=MAX_DEPLOYED)


class WaitAction(BaseModel):
    """等待动作：不操作。"""
    type: Literal["wait"] = "wait"


class ActionSpaceV2(BaseModel):
    """
    形式化动作空间：当前状态下所有合法动作的枚举。

    搜索层可以直接遍历这个空间，评估每个动作的价值。
    动作索引 = 在 actions 列表中的位置。
    """
    actions: List = Field(default_factory=list)  # DeployAction|SkillAction|RetreatAction|WaitAction
    # 各类型动作的数量，便于索引定位
    deploy_count: int = 0
    skill_count: int = 0
    retreat_count: int = 0
    wait_count: int = 1  # wait 恒为 1

    def total(self) -> int:
        return len(self.actions)

    def get(self, idx: int):
        """按索引取动作。"""
        return self.actions[idx]

    def deploy_actions(self) -> List:
        return self.actions[:self.deploy_count]

    def skill_actions(self) -> List:
        start = self.deploy_count
        return self.actions[start:start + self.skill_count]

    def retreat_actions(self) -> List:
        start = self.deploy_count + self.skill_count
        return self.actions[start:start + self.retreat_count]
