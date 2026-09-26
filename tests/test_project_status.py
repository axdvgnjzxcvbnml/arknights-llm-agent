"""scripts/project_status.py 单元测试。

覆盖：
- check_modules：模块文件完整性
- check_data：数据目录检查
- check_configs：配置完整性
- check_tests：测试统计
- main：端到端运行（返回码+JSON输出）
"""
import json
import os
import sys

import pytest

# 把项目根加入 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.project_status import (  # noqa: E402
    MODULE_FILES, CONFIG_REQUIRED_FIELDS, check_modules, check_data,
    check_configs, check_tests, check_git, main,
)


class TestCheckModules(object):
    def test_all_modules_have_files(self):
        """每个模块都有关键文件清单。"""
        assert len(MODULE_FILES) == 9
        for module, files in MODULE_FILES.items():
            assert len(files) > 0, "模块 %s 没有关键文件清单" % module

    def test_modules_complete(self):
        """当前项目所有模块关键文件应就位。"""
        results, all_ok = check_modules()
        assert all_ok, "有模块关键文件缺失: %s" % {
            k: v["missing"] for k, v in results.items() if v["missing"]}
        for module, info in results.items():
            assert info["status"] == "✅"

    def test_missing_file_detected(self, tmp_path, monkeypatch):
        """模拟缺失文件应被检测到。"""
        # 用一个不存在的路径测试
        monkeypatch.setattr("scripts.project_status.PROJECT_ROOT", str(tmp_path))
        results, all_ok = check_modules()
        assert not all_ok
        # 所有模块都应该报告缺失
        for info in results.values():
            assert info["status"] == "❌"
            assert len(info["missing"]) > 0


class TestCheckData(object):
    def test_data_complete(self):
        """当前项目数据目录应就位。"""
        results, all_ok = check_data()
        # prts_raw/vector_store/graph/sft_data/mock 都应存在
        assert "prts_raw" in results
        assert results["prts_raw"]["status"] == "✅"

    def test_missing_data_dir(self, tmp_path, monkeypatch):
        """数据目录不存在应被检测到。"""
        monkeypatch.setattr("scripts.project_status.PROJECT_ROOT", str(tmp_path))
        results, all_ok = check_data()
        assert not all_ok
        for info in results.values():
            assert info["status"] == "❌"


class TestCheckConfigs(object):
    def test_configs_complete(self):
        """当前项目配置应完整。"""
        results, all_ok = check_configs()
        assert all_ok, "有配置缺失: %s" % {
            k: v for k, v in results.items() if v["status"] != "✅"}

    def test_all_config_files_listed(self):
        """所有 configs/*.yaml 都应在检查清单中。"""
        config_dir = os.path.join(PROJECT_ROOT, "configs")
        yaml_files = [f for f in os.listdir(config_dir) if f.endswith(".yaml")]
        for yf in yaml_files:
            assert "configs/%s" % yf in CONFIG_REQUIRED_FIELDS, \
                "配置文件 %s 未在检查清单中" % yf


class TestCheckTests(object):
    def test_test_count(self):
        """测试文件和函数数应大于0。"""
        result = check_tests()
        assert result["test_files"] > 0
        assert result["test_functions"] > 0
        assert result["test_functions"] >= result["test_files"]


class TestCheckGit(object):
    def test_git_branch(self):
        """Git 分支应能获取。"""
        result = check_git()
        assert "branch" in result
        assert "commit" in result
        assert result["branch"] != "unknown"  # 当前在 git 仓库中


class TestMain(object):
    def test_main_runs(self, tmp_path, monkeypatch, capsys):
        """main() 应能完整运行并输出 JSON。"""
        # 重定向输出路径到临时目录
        out_json = os.path.join(str(tmp_path), "status.json")
        monkeypatch.setattr("scripts.project_status.OUTPUT_JSON", out_json)

        return_code = main()
        # paddleocr 未安装会导致依赖检查不通过，返回码可能是1
        assert return_code in (0, 1)

        # JSON 应已生成
        assert os.path.exists(out_json)
        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "modules" in data
        assert "data" in data
        assert "dependencies" in data
        assert "configs" in data
        assert "git" in data
        assert "tests" in data
        assert "summary" in data

    def test_main_output_has_summary(self, capsys):
        """main() 输出应包含总结行。"""
        main()
        captured = capsys.readouterr()
        assert "项目状态总览" in captured.out
        assert "总结" in captured.out
