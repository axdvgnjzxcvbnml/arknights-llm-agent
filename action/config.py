"""动作模块配置加载：读 configs/action.yaml，并合并 perception.yaml 的 coords。

坐标（grid / operator_card_bar / skill_buttons）只在 configs/perception.yaml 维护，
本加载器把其 coords 段挂到 action 配置的 cfg["coords"]，保证坐标单一来源。
"""

import os

import yaml

__all__ = ["DEFAULT_CONFIG_PATH", "load_action_config"]

DEFAULT_CONFIG_PATH = os.path.join("configs", "action.yaml")


def _read_yaml(path):
    if not os.path.exists(path):
        raise FileNotFoundError("配置文件不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_action_config(path=DEFAULT_CONFIG_PATH):
    # type: (str) -> dict
    cfg = _read_yaml(path)
    for section in ("adb", "timing", "cards", "deploy", "retreat"):
        if section not in cfg:
            raise ValueError("动作配置 %s 缺少 %s 段" % (path, section))
    # 合并 perception 的坐标段（perception_config 相对仓库根，默认在仓库根运行）
    perc_path = cfg.get("perception_config",
                        os.path.join("configs", "perception.yaml"))
    if os.path.isabs(path) and not os.path.isabs(perc_path):
        # 若用绝对路径指定 action.yaml，则相对该文件所在目录解析
        perc_path = os.path.join(os.path.dirname(path), os.path.basename(perc_path))
    perc = _read_yaml(perc_path)
    if "coords" not in perc:
        raise ValueError("视觉配置 %s 缺少 coords 段" % perc_path)
    cfg["coords"] = perc["coords"]
    cfg["device_adb"] = perc.get("adb", {})
    cfg["_perception_config_path"] = perc_path
    return cfg
