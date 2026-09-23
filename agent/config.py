"""Agent 配置加载：读 configs/agent.yaml（模型/桥接/知识/循环/Prompt 路径）。"""

import os

import yaml

__all__ = ["DEFAULT_CONFIG_PATH", "load_agent_config"]

DEFAULT_CONFIG_PATH = os.path.join("configs", "agent.yaml")


def load_agent_config(path=DEFAULT_CONFIG_PATH):
    # type: (str) -> dict
    if not os.path.exists(path):
        raise FileNotFoundError("Agent 配置文件不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    for section in ("models", "latent_bridge", "knowledge", "loop", "prompt"):
        if section not in cfg:
            raise ValueError("Agent 配置 %s 缺少 %s 段" % (path, section))
    return cfg
