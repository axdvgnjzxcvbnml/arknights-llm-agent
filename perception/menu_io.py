# TODO-V100: 非对战菜单界面的真实视觉解析统一在 V100/真机阶段接入（坐标当前为占位）。
"""非对战界面（登录/抽卡/商店）的共享配置与工具（第十五批 任务二·2）。

只依赖 pydantic/pyyaml，import 不拉起 numpy/cv2/torch。
"""

import os

try:
    import yaml
except Exception:  # pragma: no cover - CI 会装 pyyaml
    yaml = None

DEFAULT_CONFIG_PATH = os.path.join("configs", "menu.yaml")

MENU_EVIDENCE_MOCK = "mock"
MENU_EVIDENCE_CV = "cv"
MENU_EVIDENCE_VLM = "vlm"
MENU_EVIDENCE_REAL = MENU_EVIDENCE_CV

REQUIRED_SECTIONS = ["login", "gacha", "shop", "screen"]


def load_menu_config(path=DEFAULT_CONFIG_PATH):
    if not os.path.exists(path):
        raise FileNotFoundError("菜单配置不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if yaml is None:
        raise RuntimeError("缺少 pyyaml，无法加载 %s" % path)
    cfg = yaml.safe_load(text) or {}
    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing:
        raise ValueError("configs/menu.yaml 缺少必需节: %s" % ", ".join(missing))
    return cfg


def is_calibrated(config):
    """坐标是否已真机校准（占位配置为 false，真实执行器据此拒绝盲点）。"""
    return bool((config or {}).get("calibrated", False))


def is_placeholder_point(xy):
    """[-1,-1] 占位坐标判定。"""
    try:
        return len(xy) < 2 or int(xy[0]) < 0 or int(xy[1]) < 0
    except (TypeError, ValueError):
        return True
