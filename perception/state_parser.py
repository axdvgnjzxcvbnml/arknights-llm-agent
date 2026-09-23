# TODO-V100: 本模块只做"组装 + 计时推算 + mock"，不做 CV 推理；YOLO/OCR 真实读数
# 在对应模块（detector_yolo/ocr_cost/map_parser）于 V100/真机侧填充后注入。
"""游戏状态解析：把快通道各 CV 组件输出组装成结构化 GameState。

- StateParser.assemble(...)：纯组装（不碰图像/模型），把费用、手牌、已部署、技能、
  敌情、地图合成一个 GameState，供 state_to_text 与 Agent 使用。
- SpawnTracker：第一版敌情"关卡敌情表 + 计时推算"。有标注时间轴用标注，否则按固定
  间隔均匀估算（timing_source=estimated）；YOLO 后续只做"敌人是否已出现"的确认。
- MockStateParser：程序生成确定性假状态（无真实游戏数据），用于 CPU 全链路冒烟。
"""

import time
from typing import Dict, List, Optional, Sequence, Tuple

from .config import DEFAULT_CONFIG_PATH, load_perception_config
from .schemas import (CostStatus, DeployedOperator, EnemyPresence, FrameMeta,
                      GameMap, GameState, GridCell, OperatorCard, SkillStatus,
                      SpawnEntry)

__all__ = ["StateParser", "SpawnTracker", "MockStateParser", "build_grid",
           "cell_id", "iter_stage_enemies"]


def cell_id(col, row):
    # type: (int, int) -> str
    """列字母 + 行号：col=0,row=0 -> 'A1'。列超过 Z 用双字母（AA）。"""
    label = ""
    n = col
    while True:
        label = chr(ord("A") + n % 26) + label
        n = n // 26 - 1
        if n < 0:
            break
    return "%s%d" % (label, row + 1)


def iter_stage_enemies(stage_info):
    # type: (object) -> List[Tuple[str, int]]
    """从 query_stage 的结果（StageOut / dict / 原始敌情行）抽 (敌人名, 数量)。"""
    if stage_info is None:
        return []
    enemies = []
    # StageOut：.enemies[].name/count；dict：enemies[*][名称/数量]
    rows = getattr(stage_info, "enemies", None)
    if rows is None and isinstance(stage_info, dict):
        rows = stage_info.get("enemies", [])
    for row in rows or []:
        name = getattr(row, "name", None)
        count = getattr(row, "count", None)
        if name is None and isinstance(row, dict):
            name = row.get("名称") or row.get("name")
            count = row.get("数量", row.get("count", 1))
        if not name:
            continue
        try:
            count = int(str(count).strip()) if str(count).strip() else 1
        except (TypeError, ValueError):
            count = 1
        enemies.append((str(name), max(1, count)))
    return enemies


class SpawnTracker(object):
    """根据关卡敌情与（可选）标注时间轴推算波次。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_perception_config(config_path)
        spawn = cfg.get("spawn", {})
        self.interval = float(spawn.get("default_spawn_interval_sec", 6.0))
        self.timeline_cfg = spawn.get("timeline", {}) or {}

    def build_plan(self, stage_id, stage_info=None, extra_enemies=None):
        # type: (str, object, Optional[Sequence[Tuple[str, int]]]) -> Tuple[List[SpawnEntry], str]
        """返回 (spawn_plan, timing_source)。

        优先用 configs/perception.yaml 中 spawn.timeline[stage_id] 的人工标注；
        没有标注则把敌情表中每组敌人按 interval 均匀估算出场时刻。
        """
        annotated = self.timeline_cfg.get(stage_id)
        if annotated:
            plan = []
            for wave, item in enumerate(annotated):
                plan.append(SpawnEntry(
                    enemy=str(item.get("enemy", "")), count=int(item.get("count", 1)),
                    wave=wave, expected_time_sec=float(item.get("time_sec", 0.0)),
                    appeared=False, confirmed_by="timer:annotated"))
            return plan, "annotated"

        enemies = list(iter_stage_enemies(stage_info)) + list(extra_enemies or [])
        plan = []
        t = 0.0
        for wave, (name, count) in enumerate(enemies):
            plan.append(SpawnEntry(
                enemy=name, count=count, wave=wave, expected_time_sec=t,
                appeared=False, confirmed_by="timer:estimated"))
            t += self.interval
        return plan, "estimated"

    @staticmethod
    def update(plan, elapsed_sec, confirmations=None):
        # type: (List[SpawnEntry], float, Optional[Dict[str, bool]]) -> Tuple[List[SpawnEntry], List[EnemyPresence]]
        """按已用时间推进：到点的敌人计入场上；confirmations 可把某敌人标为已视觉确认。

        返回 (更新后的 plan, 当前场上敌人 EnemyPresence 列表)。
        """
        confirmations = confirmations or {}
        on_field = {}  # name -> [count, source]
        for entry in plan:
            if elapsed_sec >= entry.expected_time_sec:
                confirmed = bool(confirmations.get(entry.enemy))
                if confirmed and not entry.appeared:
                    entry.appeared = True
                    entry.confirmed_by = "cv"
                bucket = on_field.setdefault(entry.enemy, [0, entry.confirmed_by])
                bucket[0] += entry.count
                if entry.appeared:
                    bucket[1] = "cv"
        presence = [EnemyPresence(name=name, observed_count=cnt, source=src)
                    for name, (cnt, src) in on_field.items()]
        return plan, presence


class StateParser(object):
    """真实组装器：输入各组件结果，输出 GameState（纯数据拼接，无模型/IO）。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        self.config = config or load_perception_config(config_path)

    def assemble(self, frame_meta=None, stage_id="", timestamp=0.0, cost=None,
                 operator_cards=None, deployed=None, skills=None,
                 enemies_on_field=None, spawn_plan=None, timing_source="estimated",
                 game_map=None, life_points=None, deploy_used=None,
                 deploy_limit=None, notes=None):
        return GameState(
            frame=frame_meta, timestamp=timestamp, stage_id=stage_id,
            cost=cost, life_points=life_points,
            deploy_used=deploy_used, deploy_limit=deploy_limit,
            operator_cards=list(operator_cards or []),
            deployed=list(deployed or []),
            skills=list(skills or []),
            enemies_on_field=list(enemies_on_field or []),
            spawn_plan=list(spawn_plan or []),
            game_map=game_map, timing_source=timing_source,
            notes=list(notes or []),
        )

    def parse(self, frame_meta, stage_id, elapsed_sec, spawn_tracker, stage_info=None,
              cost=None, operator_cards=None, deployed=None, skills=None,
              game_map=None, life_points=None, deploy_used=None, deploy_limit=None,
              confirmations=None):
        # type: (...) -> GameState
        """完整一步：波次推算 + 组装。CV 读数由调用方（后续 perception 模块）传入。"""
        plan, timing_source = spawn_tracker.build_plan(stage_id, stage_info)
        plan, presence = SpawnTracker.update(plan, elapsed_sec, confirmations)
        notes = []
        if timing_source == "estimated":
            notes.append("敌情出场时间为按固定间隔的均匀估算（估算值，"
                         "timing_source=estimated），非精确波次；真机阶段第一步需逐关"
                         "录制真实出场时间轴回填 spawn.timeline 校准，校准前勿据此做高风险决策。")
        return self.assemble(
            frame_meta=frame_meta, stage_id=stage_id,
            timestamp=float(elapsed_sec),  # 对局内经过秒数（不是墙上时钟）
            cost=cost, operator_cards=operator_cards, deployed=deployed,
            skills=skills, enemies_on_field=presence, spawn_plan=plan,
            timing_source=timing_source, game_map=game_map,
            life_points=life_points, deploy_used=deploy_used,
            deploy_limit=deploy_limit, notes=notes)


def build_grid(cols, rows, blocked=None, occupied=None, highland=None):
    # type: (int, int, Optional[set], Optional[set], Optional[set]) -> GameMap
    """按 (col,row) 集合构造地图；默认全部为可部署地面格。"""
    blocked = blocked or set()
    occupied = occupied or set()
    highland = highland or set()
    cells = []
    for col in range(cols):
        for row in range(rows):
            key = (col, row)
            if key in blocked:
                terrain = "blocked"
                deployable = False
            else:
                terrain = "highland" if key in highland else "ground"
                deployable = True
            cells.append(GridCell(
                cell_id=cell_id(col, row), col=col, row=row,
                terrain=terrain, deployable=deployable, occupied=key in occupied))
    return GameMap(cols=cols, rows=rows, cells=cells)


class MockStateParser(object):
    """确定性假状态：对应 architecture.md 的 mock 全链路，无真实游戏数据。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH, stage_id="3-8"):
        self.config = config or load_perception_config(config_path)
        self.stage_id = stage_id
        self.tracker = SpawnTracker(config=self.config)

    def _frame_meta(self):
        cap = self.config["capture"]
        return FrameMeta(width=int(cap["width"]), height=int(cap["height"]),
                         channels=int(cap.get("channels", 3)), source="mock",
                         timestamp=time.time())

    def get_state(self, elapsed_sec=12.0, frame_meta=None):
        # type: (float, Optional[FrameMeta]) -> GameState
        frame_meta = frame_meta or self._frame_meta()
        # 地图复用 MockMapParser 的固定布局（单一布局来源），把已部署的 E4 标为占用
        from .map_parser import MockMapParser
        game_map = MockMapParser(config=self.config).set_occupied(
            ["E4"], cache_key=self.stage_id)

        # 敌情表（与 query_stage('3-8') 的种类对齐，数量为合成占位）
        stage_info = {"enemies": [
            {"名称": "源石虫", "数量": 3},
            {"名称": "猎犬", "数量": 2},
            {"名称": "重装敌人", "数量": 3},
        ]}
        plan, timing = self.tracker.build_plan(self.stage_id, stage_info)
        # mock 假设源石虫已被视觉确认出现
        confirmations = {"源石虫": True}
        plan, presence = SpawnTracker.update(plan, elapsed_sec, confirmations)
        for p in presence:
            p.position_hint = "左侧"

        cards = [
            OperatorCard(name="翎羽", operator_class="先锋", cost=2, slot=0, available=True),
            OperatorCard(name="克洛丝", operator_class="狙击", cost=3, slot=1, available=True),
            OperatorCard(name="安赛尔", operator_class="医疗", cost=3, slot=2, available=True),
        ]
        deployed = [DeployedOperator(name="芬", cell_id="E4", direction="left", hp_ratio=1.0)]
        skills = [SkillStatus(operator="芬", slot=0, ready=False, active=False,
                              sp_text="0/10", confidence=0.0, source="mock")]

        parser = StateParser(config=self.config)
        notes = ["mock 合成状态：所有读数为程序生成，不来自真实游戏画面。"]
        if timing == "estimated":
            notes.append("敌情出场时间为按固定间隔的均匀估算（估算值，"
                         "timing_source=estimated），非精确波次；真机阶段第一步需逐关"
                         "录制真实出场时间轴回填 spawn.timeline 校准，校准前勿据此做高风险决策。")
        return parser.assemble(
            frame_meta=frame_meta, stage_id=self.stage_id, timestamp=float(elapsed_sec),
            cost=CostStatus(current=15, limit=99, confidence=1.0, source="mock"),
            operator_cards=cards, deployed=deployed, skills=skills,
            enemies_on_field=presence, spawn_plan=plan, timing_source=timing,
            game_map=game_map, life_points=3, deploy_used=1, deploy_limit=9,
            notes=notes)
