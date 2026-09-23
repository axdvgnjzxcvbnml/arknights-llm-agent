# 地图格子解析以传统 CV（颜色/边缘/模板）为主，CPU 即可；真机阶段实现 _detect。
# 本沙箱只提供 MockMapParser 固定布局，用于打通链路与 state_to_text。
"""地图格子解析：从截图得到地形/可部署/已占用格子。

- MapParser：真实解析骨架。关卡开局地形是静态的，按 cache_key（通常是关卡编号）缓存
  GameMap，之后直接复用，不逐帧重算；只有"已占用"会随部署变化（第一版用动作回写，不重解析）。
- MockMapParser：返回固定 10×10 布局，默认仅 A1-A5、B1-B5 可部署（地面），其余 blocked。

坐标/网格参数从 configs/perception.yaml 的 coords.map_region 与 coords.grid 读取。
import 本模块不拉起 cv2（真实 _detect 在真机阶段实现时再用）。
"""

from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from .config import DEFAULT_CONFIG_PATH, load_perception_config
from .schemas import GameMap, GridCell

__all__ = ["MapParser", "MockMapParser", "cell_to_colrow", "default_deployable_ids"]


def cell_to_colrow(cell_id):
    # type: (str) -> Tuple[int, int]
    """'A1' -> (0,0)；支持双字母 'AA1' -> (26,0)。row 从 1 起、内部 0 基。"""
    i = 0
    while i < len(cell_id) and cell_id[i].isalpha():
        i += 1
    letters, digits = cell_id[:i], cell_id[i:]
    if not letters or not digits:
        raise ValueError("非法格子 id：%r（应为字母列+数字行，如 A1）" % cell_id)
    col = 0
    for ch in letters.upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    col -= 1
    row = int(digits) - 1
    return col, row


def default_deployable_ids():
    # type: () -> List[str]
    return ["%s%d" % (c, r) for c in ("A", "B") for r in range(1, 6)]


def _col_letter(col):
    # type: (int) -> str
    if col < 26:
        return chr(ord("A") + col)
    label = ""
    n = col
    while n >= 0:
        label = chr(ord("A") + n % 26) + label
        n = n // 26 - 1
    return label


class MapParser(object):
    """真实地图解析骨架 + 布局缓存。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_perception_config(config_path)
        coords = cfg["coords"]
        grid = coords["grid"]
        self.map_region = tuple(coords.get("map_region", [0, 0, 0, 0]))
        self.origin = tuple(grid.get("origin", [0, 0]))
        self.cell_step = tuple(grid.get("cell", [0, 0]))
        self.cols = int(grid.get("cols", 10))
        self.rows = int(grid.get("rows", 10))
        self._cache = {}  # type: Dict[str, GameMap]

    # ---- 缓存 ----
    def has_cache(self, cache_key):
        return cache_key in self._cache

    def cached_keys(self):
        return list(self._cache.keys())

    def clear_cache(self):
        self._cache.clear()

    def parse(self, frame=None, cache_key="default", force=False):
        # type: (Optional[np.ndarray], str, bool) -> GameMap
        """返回该关卡地图布局；命中缓存直接复用（不要求传 frame）。"""
        if not force and cache_key in self._cache:
            return self._cache[cache_key]
        game_map = self._detect(frame)
        self._cache[cache_key] = game_map
        return game_map

    # ---- 真实解析（真机阶段实现）----
    def _detect(self, frame):
        # type: (Optional[np.ndarray]) -> GameMap
        raise NotImplementedError(
            "TODO 真机阶段：基于 coords.map_region + coords.grid(origin/cell)，用颜色/"
            "边缘/模板分割判定每格 terrain(地面/高台/不可通行) 与是否可部署，结合动作回写"
            "occupied，返回 GameMap。CPU 传统 CV 即可；训练无关。")


class MockMapParser(MapParser):
    """固定 10×10 布局：默认仅 A1-A5、B1-B5 为可部署地面，其余 blocked。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH,
                 deployable_ids=None, occupied_ids=None, highland_ids=None):
        super(MockMapParser, self).__init__(config=config, config_path=config_path)
        self._deployable = self._ids_to_set(
            deployable_ids if deployable_ids is not None else default_deployable_ids())
        self._occupied = self._ids_to_set(occupied_ids or [])
        self._highland = self._ids_to_set(highland_ids or [])

    @staticmethod
    def _ids_to_set(ids):
        # type: (List[str]) -> Set[Tuple[int, int]]
        return {cell_to_colrow(cid) for cid in ids}

    def _detect(self, frame):
        cells = []
        for col in range(self.cols):
            for row in range(self.rows):
                key = (col, row)
                if key in self._occupied:
                    terrain, deployable, occupied = "ground", True, True
                elif key in self._deployable:
                    terrain = "highland" if key in self._highland else "ground"
                    deployable, occupied = True, False
                else:
                    terrain, deployable, occupied = "blocked", False, False
                cells.append(GridCell(
                    cell_id="%s%d" % (_col_letter(col), row + 1),
                    col=col, row=row, terrain=terrain,
                    deployable=deployable, occupied=occupied))
        return GameMap(cols=self.cols, rows=self.rows, cells=cells)

    def set_occupied(self, cell_ids, cache_key="default"):
        # type: (List[str], str) -> GameMap
        """动作层部署/撤退后回写占用状态（基于缓存的静态地形）。"""
        self._occupied = self._ids_to_set(cell_ids)
        return self.parse(cache_key=cache_key, force=True)
