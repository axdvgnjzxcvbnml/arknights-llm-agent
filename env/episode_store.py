# 对局日志存储：EpisodeLog JSON 落盘/读取（纯 CPU、无 Web 框架依赖）。
"""EpisodeStore —— 对局日志的统一读写入口。

放在 env 包（而非 api 层），使得：
- ``ArknightsEnv.run_episode(save=True)`` 结束时可**自动落盘**，不反向依赖 FastAPI；
- ``api.server`` 与环境共用同一份存储格式（``results/episodes/<id>.json``），
  避免 env 写一套、API 读一套造成漂移。

文件内容为 ``EpisodeLog.model_dump()``（EnvStep 内嵌的 ``trace`` 为完整可解释数据）。
``results/`` 已在 .gitignore，对局数据不会进入公开仓库。
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

__all__ = ["DEFAULT_EPISODE_DIR", "InvalidEpisodeId", "EpisodeStore", "safe_episode_id"]

DEFAULT_EPISODE_DIR = os.path.join("results", "episodes")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class InvalidEpisodeId(ValueError):
    """episode id 含非法字符（仅允许字母数字、下划线、连字符）。"""


def safe_episode_id(raw):
    # type: (str) -> str
    """把任意字符串（如关卡编号）规整为安全文件名片段，不保证唯一。"""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(raw or "episode")).strip("-_")
    return cleaned or "episode"


class EpisodeStore(object):
    """一个文件对应一局：``<dir>/<id>.json``。"""

    def __init__(self, directory=DEFAULT_EPISODE_DIR):
        # type: (str) -> None
        self.directory = directory

    @staticmethod
    def check_id(episode_id):
        # type: (str) -> str
        if not _SAFE_ID.match(episode_id or ""):
            raise InvalidEpisodeId(
                "非法 episode id（仅允许字母数字 _ -，1-128 位）：%r" % episode_id)
        return episode_id

    def _path(self, episode_id):
        # type: (str) -> str
        return os.path.join(self.directory, self.check_id(episode_id) + ".json")

    def exists(self, episode_id):
        # type: (str) -> bool
        return os.path.isfile(self._path(episode_id))

    def get(self, episode_id):
        # type: (str) -> Optional[Dict[str, Any]]
        path = self._path(episode_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_ids(self):
        # type: () -> List[str]
        if not os.path.isdir(self.directory):
            return []
        out = []
        for fn in os.listdir(self.directory):
            if fn.endswith(".json"):
                out.append(fn[:-len(".json")])
        return sorted(out)

    def list_meta(self):
        # type: () -> List[Dict[str, Any]]
        """轻量列表：只读每局摘要字段（不返回 steps 大字段）。"""
        metas = []
        for eid in self.list_ids():
            data = self.get(eid) or {}
            steps = data.get("steps", []) if isinstance(data, dict) else []
            reward = data.get("reward") if isinstance(data, dict) else None
            metas.append({
                "id": eid,
                "stage_id": data.get("stage_id", "") if isinstance(data, dict) else "",
                "outcome": data.get("outcome", "") if isinstance(data, dict) else "",
                "backend": data.get("backend", "") if isinstance(data, dict) else "",
                "step_count": len(steps),
                "duration_sec": data.get("duration_sec", 0.0) if isinstance(data, dict) else 0.0,
                "total_reward": (reward or {}).get("total") if isinstance(reward, dict) else None,
            })
        return metas

    def save(self, episode_id, data):
        # type: (str, Dict[str, Any]) -> str
        path = self._path(episode_id)
        os.makedirs(self.directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
