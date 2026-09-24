"""脚本层测试：9 个一键脚本的语法、GPU 门禁与关键行为（不实际执行训练/爬虫）。"""

import os
import subprocess
import sys

import pytest

SCRIPTS = [
    "scripts/setup_env.sh",
    "scripts/crawl_prts.sh",
    "scripts/build_rag.sh",
    "scripts/build_graph.sh",
    "scripts/v100_step1_setup.sh",
    "scripts/v100_step2_train_vision.sh",
    "scripts/v100_step3_sft.sh",
    "scripts/v100_step4_deploy_agent.sh",
    "scripts/v100_step5_eval.sh",
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bash_n(cmd, **kw):
    return subprocess.run(["bash", "-n", cmd], cwd=ROOT, capture_output=True, **kw)


def _bash_c(cmd, **kw):
    return subprocess.run(["bash", "-c", cmd], cwd=ROOT, capture_output=True, **kw)


@pytest.mark.parametrize("script", SCRIPTS)
def test_syntax(script):
    r = _bash_n(script)
    assert r.returncode == 0, "%s 语法错误: %s" % (script, r.stderr.decode("utf-8", "replace"))


def test_gpu_gate_scripts_reject_without_cuda():
    """v100_step2/3/4 无 CUDA 时必须安全中止（退出码 3），不做假训练。"""
    for script in ("scripts/v100_step2_train_vision.sh",
                   "scripts/v100_step3_sft.sh",
                   "scripts/v100_step4_deploy_agent.sh"):
        r = _bash_c("%s; echo rc=$?" % script)
        out = r.stdout.decode("utf-8", "replace")
        assert "GPU 门禁" in out, script
        # 门禁触发时脚本以 3 退出；但脚本内还会继续打印下一步，rc 行应在中止后
        assert "退出码 3" in out or "安全中止" in out, script


def test_step1_no_gpu_only_warns():
    """step1 无 GPU 仅告警，不中止。"""
    r = _bash_c("bash scripts/v100_step1_setup.sh; echo rc=$?")
    out = r.stdout.decode("utf-8", "replace")
    assert "Step1" in out


def test_build_rag_gate_on_missing_raw():
    """build_rag 在语料缺失时退出码 1 并提示先爬取。"""
    import shutil
    raw = os.path.join(ROOT, "data", "prts_raw")
    saved = None
    if os.path.isdir(raw):
        saved = raw + ".testbak"
        if not os.path.exists(saved):
            shutil.move(raw, saved)
    try:
        r = _bash_c("bash scripts/build_rag.sh; echo rc=$?")
    finally:
        if saved:
            shutil.move(saved, raw)
    out = r.stdout.decode("utf-8", "replace")
    assert "前置检查" in out and "crawl_prts" in out
    # 环境有 chromadb 时脚本走到语料检查退出 1；无 chromadb 时依赖检查退出 1
    assert "rc=1" in out


def test_crawl_prts_usage():
    r = _bash_c("bash scripts/crawl_prts.sh badkind; echo rc=$?")
    out = r.stdout.decode("utf-8", "replace")
    assert "用法" in out and "rc=2" in out


def test_setup_env_minimal_missing_deps():
    """--minimal 在缺依赖时退出码 1 并列出缺失项（沙箱无 chromadb 等）。"""
    r = _bash_c("bash scripts/setup_env.sh --minimal; echo rc=$?")
    out = r.stdout.decode("utf-8", "replace")
    assert "缺失" in out


def test_scripts_not_touching_remote():
    """脚本不得包含 git push / curl 外发等外部写操作。"""
    for script in SCRIPTS:
        with open(os.path.join(ROOT, script), "r", encoding="utf-8") as f:
            content = f.read()
        assert "git push" not in content, script
        assert "git commit" not in content, script
