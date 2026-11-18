"""生成泡普卡射程对照题，或汇总 run.py 输出的 JSONL 答卷。"""
import argparse
import json
from pathlib import Path


# 同一关卡局部坐标约定：列向右递增，行向下递增。
# 每个朝向都由前、后各一格构成一对；两种作答顺序由 run.py 控制。
FRONT_AND_BACK = (
    ("左", "E4", "G4"),
    ("右", "G4", "E4"),
    ("上", "F3", "F5"),
    ("下", "F5", "F3"),
)


def build_cases():
    candidates = [
        {"action": "skill", "operator_id": "泡普卡", "skill_id": 1},
        {"action": "wait", "duration_ms": 500},
    ]
    cases = []
    for pair, (facing, front, back) in enumerate(FRONT_AND_BACK, 1):
        # 题内原序固定为开技、等待，评分器会把倒序回答映射回原序。
        for enemy, correct_option in ((front, 1), (back, 2)):
            for representation in ("relative", "cells"):
                observation = {
                    "坐标": "列字母向右递增，行号向下递增。",
                    "干员": "泡普卡在F4，面朝" + facing,
                    "目标": "唯一敌人是普通地面兵，当前格为" + enemy,
                    "技能": "一技能已就绪，只提高自身攻击力，持续20秒。攻击范围为自身和正前方相邻一格。",
                }
                if representation == "cells":
                    observation["攻击覆盖格"] = ["F4", front]
                cases.append({
                    "id": "R%d-%d-%s" % (pair, correct_option, representation),
                    "stage": "合成局部棋盘",
                    "observation": observation,
                    "goal": "要强化此刻能打到敌人的攻击。此刻没有可攻击的目标时保留技能，半秒后再判断。",
                    "candidates": candidates,
                    "accepted_options": [correct_option],
                })
    return cases


def summarize(rows):
    orders = ("original", "reversed")
    expected = {(c["id"], order) for c in build_cases() for order in orders}
    answers = {(r["id"], r["order"]): r["accepted"] for r in rows}
    if set(answers) != expected or len(rows) != len(expected):
        raise ValueError("答卷须包含每题的正序和倒序回答各一次")
    result = {}
    for representation in ("relative", "cells"):
        pairs = [
            [answers["R%d-%d-%s" % (pair, position, representation), order]
             for position in (1, 2)]
            for pair in range(1, len(FRONT_AND_BACK) + 1) for order in orders
        ]
        result[representation] = {
            "correct_actions": sum(sum(pair) for pair in pairs),
            "total_actions": 2 * len(pairs),
            "both_correct": sum(all(pair) for pair in pairs),
            "total_pairs": len(pairs),
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, help="评测器生成的完整 JSONL 答卷")
    args = parser.parse_args()
    if args.score:
        rows = [json.loads(line) for line in args.score.read_text(encoding="utf-8").splitlines()]
        output = summarize(rows)
    else:
        output = build_cases()
    print(json.dumps(output, indent=2, ensure_ascii=False))
