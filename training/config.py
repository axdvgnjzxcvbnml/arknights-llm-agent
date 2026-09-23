"""训练配置加载（轻量：仅依赖 pyyaml，import 不拉起 torch）。"""

import os

import yaml

__all__ = ["load_training_config", "training_config_path"]


def training_config_path():
    # type: () -> str
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "configs", "training.yaml")


def load_training_config(path=None):
    # type: (str | None) -> dict
    p = path or training_config_path()
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
