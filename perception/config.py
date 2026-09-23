"""视觉配置加载工具（读取 configs/perception.yaml）。"""

import os

import yaml

__all__ = ["DEFAULT_CONFIG_PATH", "load_perception_config"]

DEFAULT_CONFIG_PATH = os.path.join("configs", "perception.yaml")


def load_perception_config(path=DEFAULT_CONFIG_PATH):
    # type: (str) -> dict
    """返回 perception.yaml 配置 dict；文件缺失时给出明确报错。"""
    if not os.path.exists(path):
        raise FileNotFoundError("视觉配置文件不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    for section in ("adb", "capture", "coords", "models", "spawn"):
        if section not in cfg:
            raise ValueError("配置文件 %s 缺少 %s 段" % (path, section))
    return cfg
