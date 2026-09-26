#!/usr/bin/env python3
"""配置文件 schema 验证。

验证 configs/*.yaml 是否包含必填字段，字段类型是否正确。
启动时（env/api 初始化）可调用，CI 也可单独跑。

用法：
    python scripts/validate_configs.py
    # 退出码 0=全部通过，1=有错误
"""
import os
import sys
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "configs")

# 每个配置文件的 schema 定义：{section: {field: type}}
# type 可以是 str/int/float/bool/dict/list，None 表示不检查类型
SCHEMAS = {
    "agent.yaml": {
        "backend": str,
        "models": dict,
        "latent_bridge": dict,
        "knowledge": dict,
        "loop": dict,
        "prompt": dict,
    },
    "knowledge.yaml": {
        "rag": dict,
        "crawler": dict,
        "graph": dict,
    },
    "perception.yaml": {
        "adb": dict,
        "capture": dict,
        "coords": dict,
        "models": dict,
        "spawn": dict,
    },
    "action.yaml": {
        "perception_config": str,
        "adb": dict,
        "timing": dict,
        "cards": dict,
        "deploy": dict,
        "retreat": dict,
    },
    "training.yaml": {
        "model": dict,
        "qlora": dict,
        "lora": dict,
        "sft": dict,
        "dpo": dict,
        "data_prep": dict,
    },
    "menu.yaml": {
        "calibrated": bool,
        "screen": dict,
        "login": dict,
        "gacha": dict,
        "shop": dict,
        "settle_ms": int,
    },
}

# 深层字段检查：{config_file: [(path, type), ...]}
# path 用点分隔，如 "models.slow.dtype"
DEEP_FIELDS = {
    "agent.yaml": [
        ("models.slow.name", str),
        ("models.slow.dtype", str),
        ("models.fast.name", str),
        ("models.fast.dtype", str),
        ("loop.max_steps", int),
    ],
    "knowledge.yaml": [
        ("rag.embedding.model_name", str),
        ("rag.embedding.dim", int),
        ("rag.vector_store.persist_dir", str),
        ("rag.vector_store.collection", str),
        ("graph.output_dir", str),
    ],
    "perception.yaml": [
        ("adb.host", str),
        ("adb.port", int),
        ("capture.width", int),
        ("capture.height", int),
    ],
    "training.yaml": [
        ("model.sft_base_model", str),
        ("model.torch_dtype", str),
        ("lora.r", int),
        ("lora.lora_alpha", int),
        ("sft.max_length", int),
        ("sft.fp16", bool),
        ("sft.bf16", bool),
    ],
}


def _get_nested(data: Dict[str, Any], path: str) -> Tuple[bool, Any]:
    """按点路径获取嵌套值，返回 (found, value)。"""
    keys = path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
    return True, current


def _check_type(value: Any, expected_type: type) -> bool:
    """检查值类型（bool 是 int 的子类，需特殊处理）。"""
    if expected_type is bool:
        return isinstance(value, bool)
    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected_type)


def validate_config(config_file: str, config_data: Dict[str, Any]) -> List[str]:
    """验证单个配置文件，返回错误列表。"""
    errors = []
    schema = SCHEMAS.get(config_file, {})

    # 顶层字段检查
    for field, expected_type in schema.items():
        if field not in config_data:
            errors.append("[%s] 缺少必填字段: %s" % (config_file, field))
        elif not _check_type(config_data[field], expected_type):
            errors.append("[%s] 字段 %s 类型错误: 期望 %s，实际 %s" % (
                config_file, field, expected_type.__name__, type(config_data[field]).__name__))

    # 深层字段检查
    for path, expected_type in DEEP_FIELDS.get(config_file, []):
        found, value = _get_nested(config_data, path)
        if not found:
            errors.append("[%s] 缺少深层字段: %s" % (config_file, path))
        elif not _check_type(value, expected_type):
            errors.append("[%s] 字段 %s 类型错误: 期望 %s，实际 %s" % (
                config_file, path, expected_type.__name__, type(value).__name__))

    return errors


def main():
    import yaml

    all_errors = []
    configs_checked = 0

    for config_file in SCHEMAS.keys():
        path = os.path.join(CONFIG_DIR, config_file)
        if not os.path.exists(path):
            all_errors.append("[%s] 文件不存在" % config_file)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            all_errors.append("[%s] YAML 解析失败: %s" % (config_file, e))
            continue

        errors = validate_config(config_file, data)
        all_errors.extend(errors)
        configs_checked += 1

    # 输出结果
    print("=" * 60)
    print("配置文件 Schema 验证")
    print("=" * 60)
    print("检查配置文件: %d 个" % configs_checked)
    print("顶层字段: %d 个" % sum(len(s) for s in SCHEMAS.values()))
    print("深层字段: %d 个" % sum(len(d) for d in DEEP_FIELDS.values()))
    print()

    if all_errors:
        print("发现 %d 个错误:" % len(all_errors))
        for err in all_errors:
            print("  ❌ %s" % err)
        print()
        print("验证失败 ❌")
        return 1
    else:
        print("全部通过 ✅")
        return 0


if __name__ == "__main__":
    sys.exit(main())
