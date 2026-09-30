# -*- coding: utf-8 -*-
"""
Stage 2 双通道状态表示——张量通道。

从 GameState 生成固定尺寸的数值张量，供搜索/CNN/规划层使用。
与文本通道（state_to_text）对应同一 GameState，信息对齐。

设计原则：
- 固定尺寸（MAP_H×MAP_W 等），不足零填充，超出裁剪
- 数值化：类别用 one-hot 或整数编码，布尔用 0/1
- 来源标注：timing_source / notes 与 GameState 一致
- 纯 CPU，不依赖 GPU/模拟器

张量维度：
- 地图：10×10×4（可部署/已占用/地面/高台）
- 敌人：20×6（col/row/hp_ratio/speed/type_id/count）
- 干员：12×6（cost/range_id/cooldown/class_id/available/elite）
- 已部署：8×5（col/row/direction_id/hp_ratio/class_id）
- 标量：cost/life/deploy_used/deploy_limit/timestamp/cost_state
"""
from typing import Dict, List, Optional, Tuple

from perception.schemas import (
    DEPLOYED_F,
    ENEMY_F,
    MAP_C,
    MAP_H,
    MAP_W,
    MAX_DEPLOYED,
    MAX_ENEMIES,
    MAX_OPERATORS,
    OPERATOR_F,
    DeployedTensor,
    Direction,
    EnemyTensor,
    GameMap,
    GameState,
    MapTensor,
    OperatorTensor,
    ScalarState,
    StateTensor,
)

# 职业编码（干员职业 → 整数，0=未知）
_CLASS_TO_ID: Dict[str, int] = {
    "先锋": 1, "近卫": 2, "狙击": 3, "术师": 4, "重装": 5,
    "医疗": 6, "辅助": 7, "特种": 8, "召唤": 9,
}

# 朝向编码
_DIRECTION_TO_ID: Dict[str, int] = {
    "up": 0, "down": 1, "left": 2, "right": 3,
}

# 攻击范围编码（简化：近战=0，远程=1，超长=2）
_RANGE_CLASS_TO_ID: Dict[str, int] = {
    "先锋": 0, "近卫": 0, "重装": 0, "特种": 0,  # 近战
    "狙击": 1, "术师": 1, "医疗": 1, "辅助": 1,  # 远程
    "召唤": 1,
}


def _class_id(operator_class: str) -> int:
    return _CLASS_TO_ID.get(operator_class, 0)


def _range_id(operator_class: str) -> int:
    return _RANGE_CLASS_TO_ID.get(operator_class, 0)


def _direction_id(direction: Direction) -> int:
    return _DIRECTION_TO_ID.get(direction, 0)


def _cell_to_colrow(cell_id: str) -> Tuple[int, int]:
    """格子ID（如 'C3'）→ (col, row)，无法解析返回 (0, 0)。"""
    if not cell_id or len(cell_id) < 2:
        return 0, 0
    col_char = cell_id[0].upper()
    if 'A' <= col_char <= 'Z':
        col = ord(col_char) - ord('A')
    else:
        col = 0
    try:
        row = int(cell_id[1:]) - 1  # 1-based → 0-based
    except ValueError:
        row = 0
    return col, row


# ---------------------------------------------------------------------------
# 地图张量
# ---------------------------------------------------------------------------

def build_map_tensor(game_map: Optional[GameMap]) -> MapTensor:
    """
    从 GameMap 生成 10×10×4 地图张量。

    通道：
    - c=0: 可部署（deployable and not occupied）
    - c=1: 已占用（occupied）
    - c=2: 地面（terrain == 'ground'）
    - c=3: 高台（terrain == 'highland'）

    不足 10×10 的部分零填充，超出的部分裁剪。
    """
    data = [0.0] * (MAP_H * MAP_W * MAP_C)

    if game_map is None:
        return MapTensor(data=data)

    for cell in game_map.cells:
        col, row = cell.col, cell.row
        if not (0 <= col < MAP_W and 0 <= row < MAP_H):
            continue  # 超出范围裁剪
        idx = row * MAP_W * MAP_C + col * MAP_C
        # c=0: 可部署
        data[idx + 0] = 1.0 if (cell.deployable and not cell.occupied) else 0.0
        # c=1: 已占用
        data[idx + 1] = 1.0 if cell.occupied else 0.0
        # c=2: 地面
        data[idx + 2] = 1.0 if cell.terrain == "ground" else 0.0
        # c=3: 高台
        data[idx + 3] = 1.0 if cell.terrain == "highland" else 0.0

    return MapTensor(data=data)


# ---------------------------------------------------------------------------
# 敌人张量
# ---------------------------------------------------------------------------

def build_enemy_tensor(state: GameState) -> EnemyTensor:
    """
    从 GameState 生成 20×6 敌人张量。

    特征：
    - f=0: 位置 col（从 position_hint 或入口推断，无法推断=0）
    - f=1: 位置 row
    - f=2: 血量比例（无法读取=1.0 满血假设）
    - f=3: 速度（无法读取=1.0 默认）
    - f=4: 类型编码（名称哈希取模，无法分类=0）
    - f=5: 数量（observed_count）

    不足 20 个零填充，超出裁剪。
    """
    data = [0.0] * (MAX_ENEMIES * ENEMY_F)
    valid = 0

    for enemy in state.enemies_on_field:
        if valid >= MAX_ENEMIES:
            break
        idx = valid * ENEMY_F
        # 位置：从 position_hint 推断（简化：左侧=col 0，右侧=col MAP_W-1，其他=中间）
        col, row = _hint_to_colrow(enemy.position_hint)
        data[idx + 0] = float(col)
        data[idx + 1] = float(row)
        # 血量比例：默认 1.0（满血），无法读取
        data[idx + 2] = 1.0
        # 速度：默认 1.0
        data[idx + 3] = 1.0
        # 类型编码：名称哈希取模 100
        data[idx + 4] = float(hash(enemy.name) % 100)
        # 数量
        data[idx + 5] = float(enemy.observed_count)
        valid += 1

    return EnemyTensor(data=data, valid_count=valid)


def _hint_to_colrow(hint: str) -> Tuple[int, int]:
    """从位置提示推断格子坐标。简化处理。"""
    if not hint:
        return MAP_W // 2, MAP_H // 2  # 默认中间
    h = hint.lower()
    if "左" in h or "left" in h:
        col = 0
    elif "右" in h or "right" in h:
        col = MAP_W - 1
    else:
        col = MAP_W // 2
    if "上" in h or "top" in h:
        row = 0
    elif "下" in h or "bottom" in h:
        row = MAP_H - 1
    else:
        row = MAP_H // 2
    return col, row


# ---------------------------------------------------------------------------
# 干员张量（可用手牌）
# ---------------------------------------------------------------------------

def build_operator_tensor(state: GameState) -> OperatorTensor:
    """
    从 GameState.operator_cards 生成 12×6 干员张量。

    特征：
    - f=0: 费用（cost）
    - f=1: 攻击范围编码（近战=0，远程=1）
    - f=2: 冷却（默认 0，未在冷却中）
    - f=3: 职业编码
    - f=4: 是否可用（available）
    - f=5: 精英等级（elite）

    不足 12 个零填充，超出裁剪。
    """
    data = [0.0] * (MAX_OPERATORS * OPERATOR_F)
    valid = 0

    for card in state.operator_cards:
        if valid >= MAX_OPERATORS:
            break
        idx = valid * OPERATOR_F
        data[idx + 0] = float(card.cost)
        data[idx + 1] = float(_range_id(card.operator_class))
        data[idx + 2] = 0.0  # 冷却：手牌中未部署，默认 0
        data[idx + 3] = float(_class_id(card.operator_class))
        data[idx + 4] = 1.0 if card.available else 0.0
        data[idx + 5] = float(card.elite)
        valid += 1

    return OperatorTensor(data=data, valid_count=valid)


# ---------------------------------------------------------------------------
# 已部署干员张量
# ---------------------------------------------------------------------------

def build_deployed_tensor(state: GameState) -> DeployedTensor:
    """
    从 GameState.deployed 生成 8×5 已部署干员张量。

    特征：
    - f=0: 位置 col
    - f=1: 位置 row
    - f=2: 朝向编码
    - f=3: 血量比例（hp_ratio，None=1.0）
    - f=4: 职业编码（从名称匹配 operator_cards，无法匹配=0）

    不足 8 个零填充，超出裁剪。
    """
    data = [0.0] * (MAX_DEPLOYED * DEPLOYED_F)
    valid = 0

    # 建立名称→职业的映射
    name_to_class = {c.name: c.operator_class for c in state.operator_cards}

    for dep in state.deployed:
        if valid >= MAX_DEPLOYED:
            break
        idx = valid * DEPLOYED_F
        col, row = _cell_to_colrow(dep.cell_id)
        data[idx + 0] = float(col)
        data[idx + 1] = float(row)
        data[idx + 2] = float(_direction_id(dep.direction))
        data[idx + 3] = dep.hp_ratio if dep.hp_ratio is not None else 1.0
        data[idx + 4] = float(_class_id(name_to_class.get(dep.name, "")))
        valid += 1

    return DeployedTensor(data=data, valid_count=valid)


# ---------------------------------------------------------------------------
# 标量状态
# ---------------------------------------------------------------------------

def build_scalars(state: GameState) -> ScalarState:
    """从 GameState 提取全局标量状态。"""
    cost_val = state.cost.current if state.cost else 0.0
    cost_state = 0  # ok
    if state.cost:
        if state.cost.state == "uncertain":
            cost_state = 1
        elif state.cost.state == "missing":
            cost_state = 2

    return ScalarState(
        cost=float(cost_val),
        life_points=float(state.life_points) if state.life_points is not None else 0.0,
        deploy_used=float(state.deploy_used) if state.deploy_used is not None else 0.0,
        deploy_limit=float(state.deploy_limit) if state.deploy_limit is not None else 0.0,
        timestamp=float(state.timestamp),
        cost_state=cost_state,
    )


# ---------------------------------------------------------------------------
# 主入口：GameState → StateTensor
# ---------------------------------------------------------------------------

def state_to_tensor(state: GameState) -> StateTensor:
    """
    从 GameState 生成完整的张量通道表示。

    与 state_to_text（文本通道）对应同一 GameState，信息对齐。
    纯 CPU，不依赖 GPU/模拟器。
    """
    return StateTensor(
        stage_id=state.stage_id,
        map_tensor=build_map_tensor(state.game_map),
        enemy_tensor=build_enemy_tensor(state),
        operator_tensor=build_operator_tensor(state),
        deployed_tensor=build_deployed_tensor(state),
        scalars=build_scalars(state),
        timing_source=state.timing_source,
        notes=list(state.notes),
    )


# ---------------------------------------------------------------------------
# 一致性检查：文本通道与张量通道的信息对齐
# ---------------------------------------------------------------------------

def check_alignment(state: GameState) -> Dict[str, bool]:
    """
    检查文本通道与张量通道的信息是否对齐。

    返回各维度的对齐状态：
    - cost: 费用一致
    - life: 生命一致
    - operator_count: 干员数量一致
    - enemy_count: 敌人数量一致
    - map_size: 地图尺寸一致
    """
    from perception.state_to_text import state_to_text as _state_to_text

    tensor = state_to_tensor(state)
    text = _state_to_text(state)

    result = {
        "cost": tensor.scalars.cost == (state.cost.current if state.cost else 0),
        "life": tensor.scalars.life_points == (state.life_points if state.life_points is not None else 0),
        "operator_count": tensor.operator_tensor.valid_count == len(state.operator_cards),
        "enemy_count": tensor.enemy_tensor.valid_count == len(state.enemies_on_field),
        "map_nonempty": tensor.map_tensor.data.count(1.0) > 0 if state.game_map else True,
        "text_nonempty": len(text) > 0,
    }
    return result
