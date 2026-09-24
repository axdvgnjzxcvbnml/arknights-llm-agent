#!/usr/bin/env bash
# V100 Step5：端到端评估。
# - 任意机器：用 mock 环境跑评估基线（reset->step->is_done 两局 + 对局报告 + env/reward.py 口径）。
# - V100：真实对局评估需要注入真实 perception/executor（当前真机侧为 # TODO-V100）。
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

echo "===== V100 Step5：评估 ====="
echo "[eval] 1) mock 评估基线（通关/失败两局，验证奖励与对局报告）"
"$PY" scripts/smoke_env.py

if "$PY" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  echo
  echo "[eval][CUDA] 检测到 V100。"
  cat <<'MSG'
  # TODO-V100: 真实对局批量评估尚未接入——需把真实 perception(ADB+CV) 与 executor 注入
  # env.build_mock_env 的对应位置，用 env/reward.py（通关+100/漏怪-10每点/费用溢出-1每秒）
  # 批量跑分，产出 results/episode_report_*.txt，并把结果记入 docs/experiment_log.md。
  真机就绪前，本脚本仅保证 mock 评估链路可用。
MSG
else
  echo
  echo "[eval] 无 CUDA：已完成 mock 评估基线；真机批量评估属 # TODO-V100（见 v100_checklist Step6）。"
fi

echo
echo "本步骤完成。下一步："
echo "  - 把本次结果写入 docs/experiment_log.md（日期/配置/结果/备注）"
echo "  - 回看 docs/project_plan.md 勾选里程碑"
