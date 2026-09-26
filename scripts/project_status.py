#!/usr/bin/env python3
"""项目状态总览：一键检查所有模块状态、数据就位、依赖版本、配置完整性。

输出：
- 人类可读汇总表（stdout）
- JSON 结果（results/project_status.json，gitignored）

检查项：
1. 模块文件完整性（9个模块的关键文件）
2. data/ 数据就位（PRTS/RAG/图谱/SFT/mock）
3. 依赖版本（关键库是否安装、版本是否匹配 requirements.txt）
4. configs 必填字段（7个 yaml 的关键字段）
5. Git 状态（当前分支、最近 commit、工作树是否 clean）
6. 测试状态（测试文件数、测试函数数）
"""
import importlib
import json
import os
import subprocess
import sys
from collections import OrderedDict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_JSON = os.path.join(PROJECT_ROOT, "results", "project_status.json")

# 模块关键文件清单（路径相对于项目根）
MODULE_FILES = {
    "agent": [
        "agent/__init__.py", "agent/decision_loop.py", "agent/slow_thinker.py",
        "agent/fast_reactor.py", "agent/latent_bridge.py", "agent/output_schema.py",
        "agent/knowledge_port.py",
    ],
    "knowledge": [
        "knowledge/__init__.py",
        "knowledge/crawler/prts_crawler.py", "knowledge/crawler/batch_crawl.py",
        "knowledge/rag/embedding.py", "knowledge/rag/vector_store.py",
        "knowledge/rag/retriever.py", "knowledge/rag/build_rag.py",
        "knowledge/rag/bm25_index.py",
        "knowledge/graph/build_graph.py", "knowledge/graph/query_graph.py",
        "knowledge/mcp_tools/server.py", "knowledge/mcp_tools/service.py",
        "knowledge/mcp_tools/schemas.py",
        "knowledge/source_stone_tracker.py",
    ],
    "perception": [
        "perception/__init__.py", "perception/screen_capture.py",
        "perception/state_parser.py", "perception/detector_yolo.py",
        "perception/ocr_cost.py", "perception/map_parser.py",
        "perception/state_to_text.py", "perception/vlm_analyzer.py",
        "perception/schemas.py",
    ],
    "action": [
        "action/__init__.py", "action/adb_controller.py",
        "action/action_space.py", "action/action_executor.py",
    ],
    "env": [
        "env/__init__.py", "env/arknights_env.py",
        "env/mock_env.py", "env/reward.py",
        "env/episode_store.py",
    ],
    "training": [
        "training/__init__.py", "training/sft_data_prep.py",
        "training/sft_train.py", "training/dpo_train.py",
        "training/maa_job_downloader.py", "training/pre_tokenize.py",
        "training/sft_quality_audit.py",
    ],
    "api": [
        "api/__init__.py", "api/server.py", "api/live_state.py",
    ],
    "strategy": [
        "strategy/__init__.py", "strategy/operator_development.py",
    ],
    "video_extract": [
        "video_extract/__init__.py", "video_extract/downloader.py",
        "video_extract/frame_extractor.py", "video_extract/transcriber.py",
        "video_extract/chart_reader.py", "video_extract/aligner.py",
        "video_extract/structurer.py",
    ],
}

# 数据目录检查
DATA_DIRS = {
    "prts_raw": {"desc": "PRTS 原始爬取数据", "min_files": 100},
    "vector_store": {"desc": "ChromaDB 向量库", "min_files": 1},
    "graph": {"desc": "知识图谱（GraphML+pickle）", "min_files": 1},
    "sft_data": {"desc": "SFT 训练数据（JSONL）", "min_files": 1},
    "mock": {"desc": "Mock 数据（可提交）", "min_files": 1},
}

# 关键依赖（库名: 最低版本要求，None 表示不检查版本）
KEY_DEPENDENCIES = {
    "torch": None,
    "transformers": None,
    "chromadb": None,
    "sentence_transformers": "2.0",
    "pydantic": None,
    "yaml": None,  # pyyaml
    "cv2": None,  # opencv-python
    "ultralytics": None,
    "paddleocr": None,
    "redis": None,
    "fastapi": None,
    "uvicorn": None,
    "rich": None,
    "typer": None,
    "pytest": None,
    "networkx": None,
    "jieba": None,
    "rank_bm25": None,
}

# configs 必填字段（config_file: {section: [fields]}）
CONFIG_REQUIRED_FIELDS = {
    "configs/agent.yaml": {
        "models": ["slow", "fast"],
    },
    "configs/knowledge.yaml": {
        "rag": ["build", "retrieval"],
        "graph": ["output_dir"],
    },
    "configs/perception.yaml": {
        "adb": [],
        "capture": [],
        "coords": [],
        "models": [],
        "spawn": [],
    },
    "configs/action.yaml": {
        "timing": [],
        "cards": [],
    },
    "configs/training.yaml": {
        "model": ["sft_base_model", "torch_dtype"],
        "sft": ["fp16", "bf16"],
        "lora": ["r", "lora_alpha"],
    },
    "configs/menu.yaml": {},
}


def check_modules():
    """检查模块文件完整性。"""
    results = OrderedDict()
    all_ok = True
    for module, files in MODULE_FILES.items():
        missing = []
        for f in files:
            path = os.path.join(PROJECT_ROOT, f)
            if not os.path.exists(path):
                missing.append(f)
        status = "✅" if not missing else "❌"
        if missing:
            all_ok = False
        results[module] = {
            "status": status,
            "expected": len(files),
            "missing": missing,
        }
    return results, all_ok


def check_data():
    """检查 data/ 数据是否就位。"""
    results = OrderedDict()
    all_ok = True
    for dirname, info in DATA_DIRS.items():
        path = os.path.join(PROJECT_ROOT, "data", dirname)
        if not os.path.isdir(path):
            results[dirname] = {"status": "❌", "desc": info["desc"], "files": 0,
                                 "error": "目录不存在"}
            all_ok = False
            continue
        file_count = sum(1 for _ in os.walk(path) for __ in _[2])
        if file_count < info["min_files"]:
            results[dirname] = {"status": "⚠️", "desc": info["desc"], "files": file_count,
                                 "warning": "文件数少于预期 %d" % info["min_files"]}
            all_ok = False
        else:
            results[dirname] = {"status": "✅", "desc": info["desc"], "files": file_count}
    return results, all_ok


def check_dependencies():
    """检查关键依赖是否安装。"""
    results = OrderedDict()
    all_ok = True
    for lib, min_version in KEY_DEPENDENCIES.items():
        try:
            mod = importlib.import_module(lib)
            version = getattr(mod, "__version__", "unknown")
            status = "✅"
            # 简单版本检查（只比较主版本号）
            if min_version and version != "unknown":
                try:
                    major = int(version.split(".")[0])
                    min_major = int(min_version.split(".")[0])
                    if major < min_major:
                        status = "⚠️"
                        all_ok = False
                except (ValueError, IndexError):
                    pass
            results[lib] = {"status": status, "version": version}
        except ImportError:
            results[lib] = {"status": "❌", "version": None, "error": "未安装"}
            all_ok = False
    return results, all_ok


def check_configs():
    """检查 configs 必填字段。"""
    results = OrderedDict()
    all_ok = True
    try:
        import yaml
    except ImportError:
        return {"error": "pyyaml 未安装，无法检查配置"}, False

    for config_file, sections in CONFIG_REQUIRED_FIELDS.items():
        path = os.path.join(PROJECT_ROOT, config_file)
        if not os.path.exists(path):
            results[config_file] = {"status": "❌", "error": "文件不存在"}
            all_ok = False
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            results[config_file] = {"status": "❌", "error": "YAML 解析失败: %s" % exc}
            all_ok = False
            continue

        missing = []
        for section, fields in sections.items():
            if section not in cfg:
                missing.append("section: %s" % section)
                continue
            for field in fields:
                if field not in cfg[section]:
                    missing.append("%s.%s" % (section, field))

        if missing:
            results[config_file] = {"status": "⚠️", "missing": missing}
            all_ok = False
        else:
            results[config_file] = {"status": "✅"}
    return results, all_ok


def check_git():
    """检查 Git 状态。"""
    result = {}
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        result["branch"] = branch
    except Exception:
        result["branch"] = "unknown"

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        result["commit"] = commit
    except Exception:
        result["commit"] = "unknown"

    try:
        status_output = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        result["worktree_clean"] = (status_output == "")
        result["uncommitted_files"] = len(status_output.split("\n")) if status_output else 0
    except Exception:
        result["worktree_clean"] = None

    return result


def check_tests():
    """检查测试状态。"""
    tests_dir = os.path.join(PROJECT_ROOT, "tests")
    test_files = [f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")]
    test_count = 0
    for tf in test_files:
        path = os.path.join(tests_dir, tf)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("def test_"):
                    test_count += 1
    return {"test_files": len(test_files), "test_functions": test_count}


def print_report(modules, data, deps, configs, git, tests):
    """打印人类可读汇总表。"""
    print("=" * 70)
    print("项目状态总览")
    print("=" * 70)
    print()

    # Git 状态
    print("--- Git 状态 ---")
    print("  分支: %s" % git.get("branch", "unknown"))
    print("  提交: %s" % git.get("commit", "unknown"))
    clean = git.get("worktree_clean")
    if clean is True:
        print("  工作树: ✅ clean")
    elif clean is False:
        print("  工作树: ⚠️ 有 %d 个未提交文件" % git.get("uncommitted_files", 0))
    else:
        print("  工作树: unknown")
    print()

    # 模块完整性
    print("--- 模块文件完整性 ---")
    for module, info in modules.items():
        if info["status"] == "✅":
            print("  %-16s ✅ %d 个关键文件全部就位" % (module, info["expected"]))
        else:
            print("  %-16s ❌ 缺失 %d 个: %s" % (
                module, len(info["missing"]), ", ".join(info["missing"][:3])))
    print()

    # 数据就位
    print("--- data/ 数据就位 ---")
    for dirname, info in data.items():
        if info["status"] == "✅":
            print("  %-16s ✅ %s（%d 文件）" % (dirname, info["desc"], info["files"]))
        elif info["status"] == "⚠️":
            print("  %-16s ⚠️ %s（%d 文件，%s）" % (
                dirname, info["desc"], info["files"], info.get("warning", "")))
        else:
            print("  %-16s ❌ %s（%s）" % (dirname, info["desc"], info.get("error", "")))
    print()

    # 依赖
    ok_deps = sum(1 for v in deps.values() if v["status"] == "✅")
    print("--- 关键依赖（%d/%d 已安装）---" % (ok_deps, len(deps)))
    for lib, info in deps.items():
        if info["status"] == "✅":
            print("  %-22s ✅ %s" % (lib, info["version"]))
        elif info["status"] == "⚠️":
            print("  %-22s ⚠️ %s（版本偏低）" % (lib, info["version"]))
        else:
            print("  %-22s ❌ 未安装" % lib)
    print()

    # 配置
    print("--- configs 配置完整性 ---")
    for cfg_file, info in configs.items():
        if info["status"] == "✅":
            print("  %-30s ✅" % cfg_file)
        elif info["status"] == "⚠️":
            print("  %-30s ⚠️ 缺失: %s" % (cfg_file, ", ".join(info.get("missing", [])[:3])))
        else:
            print("  %-30s ❌ %s" % (cfg_file, info.get("error", "")))
    print()

    # 测试
    print("--- 测试 ---")
    print("  测试文件: %d 个" % tests["test_files"])
    print("  测试函数: %d 个" % tests["test_functions"])
    print()

    # 总结
    print("=" * 70)
    module_ok = all(v["status"] == "✅" for v in modules.values())
    data_ok = all(v["status"] == "✅" for v in data.values())
    dep_ok = all(v["status"] == "✅" for v in deps.values())
    cfg_ok = all(v["status"] == "✅" for v in configs.values())
    print("总结: 模块%s | 数据%s | 依赖%s | 配置%s" % (
        "✅" if module_ok else "❌",
        "✅" if data_ok else "❌",
        "✅" if dep_ok else "❌",
        "✅" if cfg_ok else "❌"))
    print("=" * 70)


def main():
    modules, module_ok = check_modules()
    data, data_ok = check_data()
    deps, dep_ok = check_dependencies()
    configs, cfg_ok = check_configs()
    git = check_git()
    tests = check_tests()

    print_report(modules, data, deps, configs, git, tests)

    # 保存 JSON
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    result = {
        "modules": modules,
        "data": data,
        "dependencies": deps,
        "configs": configs,
        "git": git,
        "tests": tests,
        "summary": {
            "modules_ok": module_ok,
            "data_ok": data_ok,
            "dependencies_ok": dep_ok,
            "configs_ok": cfg_ok,
        },
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\nJSON 结果已保存: %s" % OUTPUT_JSON)

    # 返回码：全部 OK 返回 0，否则返回 1
    return 0 if all([module_ok, data_ok, dep_ok, cfg_ok]) else 1


if __name__ == "__main__":
    sys.exit(main())
