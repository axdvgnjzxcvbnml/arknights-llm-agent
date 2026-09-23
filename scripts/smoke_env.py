#!/usr/bin/env python3
"""第六批 环境封装 mock 冒烟（CPU，无 GPU/模拟器）：用统一 Gym 风格接口跑完整两局。

- win：10 步通关（+100）
- lose：3 步目标耐久归零（漏 3 点，-30）

输出「对局报告」（每步状态/动作/决策理由/耗时/奖励 + 汇总）到 results/。
运行（仓库根）：python scripts/smoke_env.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from env import render_episode_report  # noqa: E402
from env.mock_env import run_mock_episode  # noqa: E402


def main():
    print("=" * 72)
    print("arknights-llm-agent 环境封装 mock 冒烟（第六批）")
    print("=" * 72)

    os.makedirs("results", exist_ok=True)
    win = run_mock_episode("win", stage_id="3-8", win_in=10)
    lose = run_mock_episode("lose", stage_id="3-8", lose_in=3)

    win_text = render_episode_report(win)
    lose_text = render_episode_report(lose)
    with open(os.path.join("results", "episode_report_win.txt"), "w",
              encoding="utf-8") as f:
        f.write(win_text + "\n")
    with open(os.path.join("results", "episode_report_lose.txt"), "w",
              encoding="utf-8") as f:
        f.write(lose_text + "\n")

    print("\n----- 通关局（节选末尾 14 行）-----")
    print("\n".join(win_text.splitlines()[-14:]))
    print("\n----- 失败局（完整）-----")
    print(lose_text)
    print("\n对局报告已写入 results/episode_report_win.txt 与 results/episode_report_lose.txt")

    checks = {
        "win结局=通关": win.outcome == "win",
        "win步数=10": len(win.steps) == 10,
        "win总分=100": win.reward.total == 100,
        "win无漏怪": win.reward.leaked == 0,
        "lose结局=失败": lose.outcome == "defeat",
        "lose步数=3": len(lose.steps) == 3,
        "lose末步生命0": lose.steps[-1].life == 0,
        "lose漏3点": lose.reward.leaked == 3,
        "lose总分=-30": lose.reward.total == -30,
        "每步有执行结果": all(s.plan_result is not None and s.plan_result.total >= 1
                             for s in win.steps + lose.steps),
        "每步有状态文本": all(s.state_text for s in win.steps + lose.steps),
        "报告含决策理由": "决策:" in win_text and "依据1:" in win_text,
        "报告含奖励明细": "奖励明细" in win_text and "奖励明细" in lose_text,
        "报告含耗时": all("耗时" in line for line in win_text.splitlines()
                         if line.startswith("步 1 ")),
    }
    failed = [k for k, ok in checks.items() if not ok]
    print("\n完整性检查: %d/%d 通过" % (len(checks) - len(failed), len(checks)))
    if failed:
        print("未通过项: %s" % failed)
        return 1
    print("ENV SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
