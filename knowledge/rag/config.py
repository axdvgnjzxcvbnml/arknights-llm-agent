"""知识库配置加载工具（读取 configs/knowledge.yaml）。"""

import os

import yaml

__all__ = ["DEFAULT_CONFIG_PATH", "load_knowledge_config"]

DEFAULT_CONFIG_PATH = os.path.join("configs", "knowledge.yaml")


def load_knowledge_config(path=DEFAULT_CONFIG_PATH):
    # type: (str) -> dict
    """返回完整 knowledge.yaml 配置 dict。文件不存在时给出明确报错。"""
    if not os.path.exists(path):
        raise FileNotFoundError("知识库配置文件不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if "rag" not in cfg:
        raise ValueError("配置文件 %s 缺少 rag 段" % path)
    return cfg
