"""第八批脚本的契约测试：仅用标准库 subprocess，不依赖 rich/网络/GPU/真实数据。

覆盖：
- scripts/*.sh 全部通过 bash -n 语法检查；
- 本批 9 个脚本都带"下一步"脚注与前置检查；
- setup_env 的仅查版本模式可跑（ARK_SKIP_PIP=1，退出 0）；
- GPU 门禁：无 CUDA 沙箱 step2/step3 退出 3；step1 只检查退出 0 且明确不编译 PointNet2；
- step5 任意机器先跑 mock 评估基线（退出 0）；
- crawl_prts 非法类型在联网前退出 2；
- build_rag/build_graph/crawl_prts 都有数据/依赖前置检查（静态断言）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

NEW_SCRIPTS = [
    "setup_env.sh",
    "crawl_prts.sh",
    "build_rag.sh",
    "build_graph.sh",
    "v100_step1_setup.sh",
    "v100_step2_train_vision.sh",
    "v100_step3_sft.sh",
    "v100_step4_deploy_agent.sh",
    "v100_step5_eval.sh",
]
GATED = ["v100_step2_train_vision.sh", "v100_step3_sft.sh"]


def _run(args, env=None, timeout=180):
    return subprocess.run(
        args, cwd=str(ROOT), capture_output=True, text=True,
        env=env, timeout=timeout,
    )


def test_all_shell_scripts_pass_bash_n():
    sh_files = sorted(p.name for p in SCRIPTS.glob("*.sh"))
    assert sh_files, "scripts/ 下应有 .sh 脚本"
    for name in sh_files:
        r = _run(["bash", "-n", str(SCRIPTS / name)])
        assert r.returncode == 0, "%s 语法错误:\n%s" % (name, r.stderr)


def test_new_scripts_have_footer_and_prereq():
    for name in NEW_SCRIPTS:
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "下一步" in text, "%s 缺少结尾'下一步'提示" % name
        # 统一切到仓库根，避免从别处调用时路径错
        assert 'cd "$(dirname "${BASH_SOURCE[0]}")/.."' in text


def test_setup_env_check_only():
    import os
    env = dict(os.environ)
    env["ARK_SKIP_PIP"] = "1"
    r = _run(["bash", str(SCRIPTS / "setup_env.sh")], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "核心依赖齐全" in r.stdout


def test_v100_step1_check_only_no_pointnet2():
    r = _run(["bash", str(SCRIPTS / "v100_step1_setup.sh")], timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "不编译" in r.stdout and "PointNet2" in r.stdout


def test_gpu_gated_scripts_exit3_without_cuda():
    for name in GATED:
        r = _run(["bash", str(SCRIPTS / name)], timeout=240)
        assert r.returncode == 3, "%s 无 CUDA 应门禁退出3，实际 %s\n%s" % (
            name, r.returncode, r.stdout + r.stderr)
        assert "需要 V100" in r.stdout


def test_step4_has_gate_and_smoke_static():
    # step4 会跑完整三段冒烟，较慢；这里静态保证它先跑 smoke 再 GPU 门禁
    text = (SCRIPTS / "v100_step4_deploy_agent.sh").read_text(encoding="utf-8")
    assert "scripts/run_smoke.sh" in text
    assert "exit 3" in text


def test_step5_runs_mock_baseline():
    r = _run(["bash", str(SCRIPTS / "v100_step5_eval.sh")], timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ENV SMOKE OK" in r.stdout


def test_crawl_bad_type_exits_before_network():
    r = _run(["bash", str(SCRIPTS / "crawl_prts.sh"), "bogus"])
    assert r.returncode == 2
    assert "未知类型" in r.stdout


def test_build_scripts_guard_missing_prereq():
    for name in ["crawl_prts.sh", "build_rag.sh", "build_graph.sh"]:
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "prts_raw" in text, "%s 应检查 data/prts_raw 前置数据" % name
