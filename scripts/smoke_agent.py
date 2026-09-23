#!/usr/bin/env python3
"""第五批 Agent mock 全链路冒烟（CPU，无 GPU/模拟器/爬虫数据）。

链路：感知(mock 演进战局) -> state_to_text -> 知识检索(mock: retrieved+inferred)
      -> 慢思考(mock 状态感知决策) -> 慢快桥接(mock) -> 快反应(即时可行性裁剪)
      -> 动作执行(MockADB) -> 自我反思，循环多步；输出可解释决策日志到 results/。

运行（仓库根）：python scripts/smoke_agent.py
退出码 0 表示"状态->思考->决策->执行"闭环与可解释字段完整；非 0 表示回归失败。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from agent import build_mock_loop, render_decision_log, write_decision_log  # noqa: E402

STAGE_ID = "3-8"
STEPS = 4


def main():
    print("=" * 72)
    print("arknights-llm-agent Agent mock 全链路冒烟（第五批）")
    print("=" * 72)

    loop = build_mock_loop()
    log = loop.run(stage_id=STAGE_ID, steps=STEPS)
    text = render_decision_log(log)

    print("\n" + "-" * 72)
    print("可解释决策日志（节选前 40 行）")
    print("-" * 72)
    print("\n".join(text.splitlines()[:40]))

    out = write_decision_log(log, log_dir="results")
    print("-" * 72)
    print("完整决策日志已写入: %s" % out)

    # ---- 关键完整性断言（回归闸门）----
    dep_steps = [r for r in log.steps[:3]]
    dep_names = [r.command.plan.actions[0].operator_id for r in dep_steps]
    checks = {
        "步数=4": len(log.steps) == 4,
        "前3步均部署": all(r.command.plan.actions[0].action == "deploy"
                          for r in dep_steps),
        "部署三个不同干员": set(dep_names) == {"翎羽", "安赛尔", "克洛丝"},
        "第4步无手牌转等待": log.steps[3].command.plan.actions[0].action == "wait",
        "执行0失败": log.failed_actions() == 0,
        "每步有reasoning": all(r.decision.reasoning.analysis for r in log.steps),
        "每步有知识引用": all(any(
            c.evidence in ("retrieved", "inferred") for c in r.decision.knowledge_used)
            for r in log.steps),
        "证据分级retrieved": "[retrieved]" in text,
        "证据分级inferred": "[inferred]" in text,
        "有慢快桥接": "慢快桥接" in text,
        "有快通道拦截说明": "快反应" in text,
        "有自我反思": all(r.reflection is not None for r in log.steps),
        "置信度在区间": all(0.0 <= r.decision.confidence <= 1.0 for r in log.steps),
        "六段延迟记录": all(
            {"perceive_ms", "knowledge_ms", "slow_ms", "bridge_ms",
             "fast_ms", "execute_ms"} <= set(r.latency_ms) for r in log.steps),
    }
    failed = [k for k, ok in checks.items() if not ok]
    print("\n完整性检查: %d/%d 通过" % (len(checks) - len(failed), len(checks)))
    if failed:
        print("未通过项: %s" % failed)
        return 1
    print("AGENT SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
