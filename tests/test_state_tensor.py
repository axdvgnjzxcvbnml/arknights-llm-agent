# -*- coding: utf-8 -*-
"""
Stage 2 双通道状态表示——单元测试。

测试：
1. 张量通道：从 GameState 生成张量，验证 shape 和数值正确
2. 动作空间：可枚举、合法性约束
3. 一致性：文本通道与张量通道信息对齐
"""
import pytest

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
    CostStatus,
    DeployAction,
    DeployedOperator,
    Direction,
    EnemyPresence,
    GameMap,
    GameState,
    GridCell,
    OperatorCard,
    RetreatAction,
    SkillAction,
    WaitAction,
)
from perception.state_tensor import (
    build_deployed_tensor,
    build_enemy_tensor,
    build_map_tensor,
    build_operator_tensor,
    build_scalars,
    check_alignment,
    state_to_tensor,
)
from perception.action_space_v2 import (
    action_description,
    build_action_space,
    estimate_space_size,
)


# ---------------------------------------------------------------------------
# Fixture：构造一个丰富的 mock GameState
# ---------------------------------------------------------------------------

def _make_grid(cols=10, rows=10, deployable_pattern=None):
    """构造测试用地图。"""
    cells = []
    for r in range(rows):
        for c in range(cols):
            cell_id = f"{chr(ord('A') + c)}{r + 1}"
            terrain = "highland" if c >= 5 else "ground"
            deployable = True
            if deployable_pattern and cell_id not in deployable_pattern:
                deployable = False
            cells.append(GridCell(
                cell_id=cell_id, col=c, row=r,
                terrain=terrain, deployable=deployable, occupied=False,
            ))
    return GameMap(cols=cols, rows=rows, cells=cells)


def _make_rich_state():
    """构造一个信息丰富的 GameState 用于测试。"""
    game_map = _make_grid()
    # 标记 E4 已占用
    for cell in game_map.cells:
        if cell.cell_id == "E4":
            cell.occupied = True

    return GameState(
        stage_id="3-8",
        timestamp=12.5,
        cost=CostStatus(current=15, limit=99, state="ok", source="mock"),
        life_points=3,
        deploy_used=1,
        deploy_limit=9,
        operator_cards=[
            OperatorCard(name="芬", operator_class="先锋", cost=2, slot=0, available=True),
            OperatorCard(name="能天使", operator_class="狙击", cost=6, slot=1, available=True),
            OperatorCard(name="安赛尔", operator_class="医疗", cost=3, slot=2, available=False),
        ],
        deployed=[
            DeployedOperator(name="芬", cell_id="E4", direction="right", hp_ratio=0.8),
        ],
        enemies_on_field=[
            EnemyPresence(name="源石虫", observed_count=3, position_hint="左侧", source="timer:estimated"),
            EnemyPresence(name="猎犬", observed_count=2, position_hint="左侧", source="timer:estimated"),
        ],
        game_map=game_map,
        timing_source="estimated",
        notes=["均匀估算波次时间轴"],
    )


# ---------------------------------------------------------------------------
# 1. 地图张量测试
# ---------------------------------------------------------------------------

class TestMapTensor:
    def test_shape(self):
        game_map = _make_grid()
        tensor = build_map_tensor(game_map)
        assert tensor.shape == [MAP_H, MAP_W, MAP_C]
        assert len(tensor.data) == MAP_H * MAP_W * MAP_C

    def test_deployable_channel(self):
        game_map = _make_grid()
        tensor = build_map_tensor(game_map)
        ch0 = tensor.channel(0)  # 可部署
        # 全部格子默认可部署（除了被占用的）
        assert ch0[0][0] == 1.0  # A1 可部署

    def test_occupied_channel(self):
        game_map = _make_grid()
        for cell in game_map.cells:
            if cell.cell_id == "E4":
                cell.occupied = True
        tensor = build_map_tensor(game_map)
        ch1 = tensor.channel(1)  # 已占用
        # E4: col=4, row=3
        assert ch1[3][4] == 1.0
        assert ch1[0][0] == 0.0  # A1 未占用

    def test_terrain_channels(self):
        game_map = _make_grid()
        tensor = build_map_tensor(game_map)
        ch2 = tensor.channel(2)  # 地面
        ch3 = tensor.channel(3)  # 高台
        # A1 (col=0) 是地面
        assert ch2[0][0] == 1.0
        assert ch3[0][0] == 0.0
        # F1 (col=5) 是高台
        assert ch2[0][5] == 0.0
        assert ch3[0][5] == 1.0

    def test_none_map(self):
        tensor = build_map_tensor(None)
        assert tensor.shape == [MAP_H, MAP_W, MAP_C]
        assert all(v == 0.0 for v in tensor.data)

    def test_out_of_bounds_cropped(self):
        """超出 10×10 的格子被裁剪。"""
        cells = [GridCell(cell_id="Z99", col=99, row=99, terrain="ground", deployable=True)]
        game_map = GameMap(cols=100, rows=100, cells=cells)
        tensor = build_map_tensor(game_map)
        # Z99 超出范围，不应出现在张量中
        assert all(v == 0.0 for v in tensor.data)


# ---------------------------------------------------------------------------
# 2. 敌人张量测试
# ---------------------------------------------------------------------------

class TestEnemyTensor:
    def test_shape_and_count(self):
        state = _make_rich_state()
        tensor = build_enemy_tensor(state)
        assert tensor.shape == [MAX_ENEMIES, ENEMY_F]
        assert tensor.valid_count == 2

    def test_enemy_features(self):
        state = _make_rich_state()
        tensor = build_enemy_tensor(state)
        e0 = tensor.enemy(0)
        assert len(e0) == ENEMY_F
        # f=5: 数量 = 3（源石虫）
        assert e0[5] == 3.0
        e1 = tensor.enemy(1)
        assert e1[5] == 2.0  # 猎犬

    def test_padding(self):
        """不足 MAX_ENEMIES 的部分零填充。"""
        state = _make_rich_state()
        tensor = build_enemy_tensor(state)
        # 第 3 个敌人（index=2）是 padding，全零
        e2 = tensor.enemy(2)
        assert all(v == 0.0 for v in e2)

    def test_empty_enemies(self):
        state = GameState()
        tensor = build_enemy_tensor(state)
        assert tensor.valid_count == 0
        assert all(v == 0.0 for v in tensor.data)


# ---------------------------------------------------------------------------
# 3. 干员张量测试
# ---------------------------------------------------------------------------

class TestOperatorTensor:
    def test_shape_and_count(self):
        state = _make_rich_state()
        tensor = build_operator_tensor(state)
        assert tensor.shape == [MAX_OPERATORS, OPERATOR_F]
        assert tensor.valid_count == 3

    def test_operator_features(self):
        state = _make_rich_state()
        tensor = build_operator_tensor(state)
        op0 = tensor.operator(0)  # 芬（先锋）
        assert op0[0] == 2.0  # 费用
        assert op0[1] == 0.0  # 近战范围编码
        assert op0[3] == 1.0  # 先锋职业编码
        assert op0[4] == 1.0  # 可用
        op1 = tensor.operator(1)  # 能天使（狙击）
        assert op1[0] == 6.0  # 费用
        assert op1[1] == 1.0  # 远程范围编码
        assert op1[3] == 3.0  # 狙击职业编码
        op2 = tensor.operator(2)  # 安赛尔（医疗，不可用）
        assert op2[4] == 0.0  # 不可用

    def test_padding(self):
        state = _make_rich_state()
        tensor = build_operator_tensor(state)
        op3 = tensor.operator(3)
        assert all(v == 0.0 for v in op3)


# ---------------------------------------------------------------------------
# 4. 已部署张量测试
# ---------------------------------------------------------------------------

class TestDeployedTensor:
    def test_shape_and_count(self):
        state = _make_rich_state()
        tensor = build_deployed_tensor(state)
        assert tensor.shape == [MAX_DEPLOYED, DEPLOYED_F]
        assert tensor.valid_count == 1

    def test_deployed_features(self):
        state = _make_rich_state()
        tensor = build_deployed_tensor(state)
        d0 = tensor.deployed if hasattr(tensor, 'deployed') else None
        # 直接从 data 取
        d0 = tensor.data[0:DEPLOYED_F]
        # E4: col=4, row=3
        assert d0[0] == 4.0  # col
        assert d0[1] == 3.0  # row
        assert d0[2] == 3.0  # direction: right=3 (up=0,down=1,left=2,right=3)
        assert d0[3] == 0.8  # hp_ratio


# ---------------------------------------------------------------------------
# 5. 标量状态测试
# ---------------------------------------------------------------------------

class TestScalarState:
    def test_basic(self):
        state = _make_rich_state()
        scalars = build_scalars(state)
        assert scalars.cost == 15.0
        assert scalars.life_points == 3.0
        assert scalars.deploy_used == 1.0
        assert scalars.deploy_limit == 9.0
        assert scalars.timestamp == 12.5
        assert scalars.cost_state == 0  # ok

    def test_uncertain_cost(self):
        state = GameState(cost=CostStatus(current=10, state="uncertain", source="mock"))
        scalars = build_scalars(state)
        assert scalars.cost_state == 1  # uncertain

    def test_missing_cost(self):
        state = GameState(cost=CostStatus(current=0, state="missing", source="mock"))
        scalars = build_scalars(state)
        assert scalars.cost_state == 2  # missing


# ---------------------------------------------------------------------------
# 6. 完整 StateTensor 测试
# ---------------------------------------------------------------------------

class TestStateTensor:
    def test_full_conversion(self):
        state = _make_rich_state()
        tensor = state_to_tensor(state)
        assert tensor.stage_id == "3-8"
        assert tensor.timing_source == "estimated"
        assert len(tensor.notes) == 1
        assert tensor.map_tensor.shape == [MAP_H, MAP_W, MAP_C]
        assert tensor.enemy_tensor.valid_count == 2
        assert tensor.operator_tensor.valid_count == 3
        assert tensor.deployed_tensor.valid_count == 1
        assert tensor.scalars.cost == 15.0

    def test_empty_state(self):
        state = GameState()
        tensor = state_to_tensor(state)
        assert tensor.enemy_tensor.valid_count == 0
        assert tensor.operator_tensor.valid_count == 0
        assert tensor.deployed_tensor.valid_count == 0


# ---------------------------------------------------------------------------
# 7. 动作空间测试
# ---------------------------------------------------------------------------

class TestActionSpace:
    def test_enumerable(self):
        state = _make_rich_state()
        space = build_action_space(state)
        assert space.total() > 0
        # 动作可按索引访问
        for i in range(space.total()):
            action = space.get(i)
            assert action is not None

    def test_wait_always_present(self):
        state = GameState()  # 空状态
        space = build_action_space(state)
        assert space.wait_count == 1
        # 最后一个动作是 wait
        last = space.get(space.total() - 1)
        assert isinstance(last, WaitAction)

    def test_deploy_actions_legal(self):
        state = _make_rich_state()
        space = build_action_space(state)
        for action in space.deploy_actions():
            assert isinstance(action, DeployAction)
            assert 0 <= action.operator_idx < MAX_OPERATORS
            assert 0 <= action.grid_col < MAP_W
            assert 0 <= action.grid_row < MAP_H
            assert action.direction in ("up", "down", "left", "right")

    def test_skill_actions(self):
        state = _make_rich_state()
        space = build_action_space(state)
        for action in space.skill_actions():
            assert isinstance(action, SkillAction)
            assert 0 <= action.deployed_idx < MAX_DEPLOYED

    def test_retreat_actions(self):
        state = _make_rich_state()
        space = build_action_space(state)
        for action in space.retreat_actions():
            assert isinstance(action, RetreatAction)
            assert 0 <= action.deployed_idx < MAX_DEPLOYED

    def test_deployed_operator_not_redeployable(self):
        """已部署的干员不能再部署。"""
        state = _make_rich_state()
        space = build_action_space(state)
        # 芬已部署（E4），不应出现在部署动作的 operator_idx 中
        # 芬是 operator_cards[0]
        deploy_op_indices = {a.operator_idx for a in space.deploy_actions()}
        assert 0 not in deploy_op_indices  # 芬已部署
        assert 1 in deploy_op_indices  # 能天使可部署

    def test_estimate_space_size(self):
        state = _make_rich_state()
        est = estimate_space_size(state)
        assert est["total"] > 0
        assert est["deploy"] > 0
        assert est["wait"] == 1
        # 估算值应与实际空间大小接近
        space = build_action_space(state)
        assert est["total"] == space.total()

    def test_action_description(self):
        assert action_description(WaitAction()) == "wait()"
        assert "deploy" in action_description(DeployAction(operator_idx=0, grid_col=1, grid_row=2, direction="up"))
        assert "skill" in action_description(SkillAction(deployed_idx=0))
        assert "retreat" in action_description(RetreatAction(deployed_idx=0))


# ---------------------------------------------------------------------------
# 8. 一致性测试（文本通道 vs 张量通道）
# ---------------------------------------------------------------------------

class TestAlignment:
    def test_cost_alignment(self):
        state = _make_rich_state()
        result = check_alignment(state)
        assert result["cost"] is True

    def test_life_alignment(self):
        state = _make_rich_state()
        result = check_alignment(state)
        assert result["life"] is True

    def test_operator_count_alignment(self):
        state = _make_rich_state()
        result = check_alignment(state)
        assert result["operator_count"] is True

    def test_enemy_count_alignment(self):
        state = _make_rich_state()
        result = check_alignment(state)
        assert result["enemy_count"] is True

    def test_text_nonempty(self):
        state = _make_rich_state()
        result = check_alignment(state)
        assert result["text_nonempty"] is True

    def test_full_alignment(self):
        """所有维度都应对齐。"""
        state = _make_rich_state()
        result = check_alignment(state)
        for key, value in result.items():
            assert value is True, f"对齐失败: {key}"


# ---------------------------------------------------------------------------
# 9. 边界测试
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_game_state(self):
        """空 GameState 不应报错。"""
        state = GameState()
        tensor = state_to_tensor(state)
        assert tensor is not None
        space = build_action_space(state)
        assert space.total() == 1  # 只有 wait

    def test_huge_operator_list(self):
        """超过 MAX_OPERATORS 的干员列表被裁剪。"""
        cards = [OperatorCard(name=f"op{i}", operator_class="先锋", cost=1) for i in range(20)]
        state = GameState(operator_cards=cards)
        tensor = build_operator_tensor(state)
        assert tensor.valid_count == MAX_OPERATORS

    def test_huge_enemy_list(self):
        enemies = [EnemyPresence(name=f"e{i}", observed_count=1) for i in range(30)]
        state = GameState(enemies_on_field=enemies)
        tensor = build_enemy_tensor(state)
        assert tensor.valid_count == MAX_ENEMIES

    def test_none_cost(self):
        state = GameState(cost=None)
        scalars = build_scalars(state)
        assert scalars.cost == 0.0
        assert scalars.cost_state == 0  # None 视为 ok

    def test_invalid_cell_id(self):
        """无效的 cell_id 不应报错。"""
        state = GameState(deployed=[DeployedOperator(name="x", cell_id="", direction="up")])
        tensor = build_deployed_tensor(state)
        assert tensor.valid_count == 1
        # 无效 cell_id 默认为 (0, 0)
        assert tensor.data[0] == 0.0  # col
        assert tensor.data[1] == 0.0  # row
