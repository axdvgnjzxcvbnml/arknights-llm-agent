"""EpisodeStore 单元测试：对局日志的读写、列表、元数据、异常路径。

用 tmp_path 隔离，不碰真实 results/episodes/。
"""

import json
import os

import pytest

from env.episode_store import (
    DEFAULT_EPISODE_DIR,
    EpisodeStore,
    InvalidEpisodeId,
    safe_episode_id,
)


class TestSafeEpisodeId:
    def test_normal(self):
        assert safe_episode_id("3-8") == "3-8"

    def test_empty(self):
        assert safe_episode_id("") == "episode"
        assert safe_episode_id(None) == "episode"

    def test_special_chars(self):
        """特殊字符和中文被替换为连字符（只保留 ASCII 字母数字 _ -）。"""
        assert safe_episode_id("3-8 黄昏!@#") == "3-8"

    def test_chinese_replaced(self):
        """纯中文被全部替换，fallback 为 episode。"""
        assert safe_episode_id("能天使的技能") == "episode"


class TestCheckId:
    def test_valid(self):
        assert EpisodeStore.check_id("abc-123_test") == "abc-123_test"

    def test_invalid_slash(self):
        with pytest.raises(InvalidEpisodeId):
            EpisodeStore.check_id("../etc/passwd")

    def test_invalid_space(self):
        with pytest.raises(InvalidEpisodeId):
            EpisodeStore.check_id("has space")

    def test_empty(self):
        with pytest.raises(InvalidEpisodeId):
            EpisodeStore.check_id("")

    def test_too_long(self):
        with pytest.raises(InvalidEpisodeId):
            EpisodeStore.check_id("a" * 129)


class TestEpisodeStoreCRUD:
    def test_save_and_get(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        data = {"stage_id": "3-8", "outcome": "win", "steps": [{"step": 1}]}
        path = store.save("ep-001", data)
        assert os.path.isfile(path)
        loaded = store.get("ep-001")
        assert loaded == data

    def test_get_nonexistent(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        assert store.get("nonexistent") is None

    def test_exists(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        assert store.exists("ep-001") is False
        store.save("ep-001", {"a": 1})
        assert store.exists("ep-001") is True

    def test_save_creates_directory(self, tmp_path):
        """save 时自动创建目录。"""
        nested = os.path.join(str(tmp_path), "sub", "dir")
        store = EpisodeStore(directory=nested)
        store.save("ep-001", {"a": 1})
        assert os.path.isdir(nested)

    def test_save_invalid_id(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        with pytest.raises(InvalidEpisodeId):
            store.save("invalid id!", {"a": 1})

    def test_get_invalid_id(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        with pytest.raises(InvalidEpisodeId):
            store.get("invalid id!")


class TestEpisodeStoreList:
    def test_list_ids_empty(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        assert store.list_ids() == []

    def test_list_ids_nonexistent_dir(self, tmp_path):
        """目录不存在时返回空列表。"""
        store = EpisodeStore(directory=os.path.join(str(tmp_path), "no_such"))
        assert store.list_ids() == []

    def test_list_ids_sorted(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        store.save("ep-002", {"a": 1})
        store.save("ep-001", {"a": 1})
        store.save("ep-003", {"a": 1})
        assert store.list_ids() == ["ep-001", "ep-002", "ep-003"]

    def test_list_ids_only_json(self, tmp_path):
        """只返回 .json 文件，忽略其他文件。"""
        store = EpisodeStore(directory=str(tmp_path))
        store.save("ep-001", {"a": 1})
        with open(os.path.join(str(tmp_path), "readme.txt"), "w") as f:
            f.write("not json")
        assert store.list_ids() == ["ep-001"]


class TestEpisodeStoreListMeta:
    def test_list_meta_empty(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        assert store.list_meta() == []

    def test_list_meta_fields(self, tmp_path):
        store = EpisodeStore(directory=str(tmp_path))
        data = {
            "stage_id": "3-8",
            "outcome": "win",
            "backend": "mock",
            "duration_sec": 12.5,
            "steps": [{"step": 1}, {"step": 2}],
            "reward": {"total": 100.0},
        }
        store.save("ep-001", data)
        metas = store.list_meta()
        assert len(metas) == 1
        m = metas[0]
        assert m["id"] == "ep-001"
        assert m["stage_id"] == "3-8"
        assert m["outcome"] == "win"
        assert m["backend"] == "mock"
        assert m["step_count"] == 2
        assert m["duration_sec"] == 12.5
        assert m["total_reward"] == 100.0

    def test_list_meta_missing_reward(self, tmp_path):
        """reward 缺失时 total_reward 为 None。"""
        store = EpisodeStore(directory=str(tmp_path))
        store.save("ep-001", {"stage_id": "3-8", "steps": []})
        m = store.list_meta()[0]
        assert m["total_reward"] is None
        assert m["step_count"] == 0

    def test_list_meta_corrupt_json_raises(self, tmp_path):
        """损坏的 JSON 文件会让 get() 抛 JSONDecodeError（当前行为，未做容错）。"""
        import json as _json
        store = EpisodeStore(directory=str(tmp_path))
        store.save("ep-001", {"stage_id": "3-8", "steps": [1]})
        with open(os.path.join(str(tmp_path), "ep-002.json"), "w") as f:
            f.write("{not valid json")
        with pytest.raises(_json.JSONDecodeError):
            store.list_meta()


class TestDefaultDir:
    def test_default_dir(self):
        assert DEFAULT_EPISODE_DIR == os.path.join("results", "episodes")
