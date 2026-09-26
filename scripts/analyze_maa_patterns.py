#!/usr/bin/env python3
"""从 data/sft_data/sft_all.jsonl 统计 MAA 作业决策模式。

统计维度：
1. 干员本体出场频率（deploy 动作，排除召唤物/装置）
2. 召唤物/装置出现频率（不在 PRTS 干员白名单中的部署对象）
3. 动作类型分布（deploy/skill/retreat/wait 比例）
4. 费用-部署关系（按 kills 进度锚点的部署时序）
5. 技能时机（skill 动作的 kills 分布）
6. 部署位置模式（坐标热力分布）
7. 关卡-阵容（每个关卡的干员组合，仅干员本体）
8. 朝向分布（远程 vs 近战的朝向偏好）

干员本体 vs 召唤物/装置的区分：
- 用 data/prts_raw/operators/ 目录的文件名作为干员白名单（460 个）
- 在白名单中的 = 干员本体；不在白名单中的 = 召唤物/装置（弦惊、障碍物、幻影等）
- 注意：部分异格干员可能因文件名差异被误分类，需人工核对

数据局限：meta 中没有 upload_time/publish_time 字段，无法按时间分组统计新干员趋势。

输出：results/maa_patterns/stats.json + 打印人类可读汇总
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

INPUT_PATH = "data/sft_data/sft_all.jsonl"
OUTPUT_DIR = "results/maa_patterns"
OPERATORS_DIR = "data/prts_raw/operators"


def load_operator_whitelist():
    """从 PRTS 干员 JSON 目录加载干员白名单（文件名即干员名）。"""
    if not os.path.isdir(OPERATORS_DIR):
        return set()
    return set(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(OPERATORS_DIR, "*.json"))
    )


def main():
    if not os.path.exists(INPUT_PATH):
        print("错误：%s 不存在，请先运行 SFT 数据准备" % INPUT_PATH)
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 加载 PRTS 干员白名单，用于区分干员本体和召唤物/装置
    operator_whitelist = load_operator_whitelist()
    print("PRTS 干员白名单: %d 个" % len(operator_whitelist))

    # 统计容器
    total = 0
    action_counter = Counter()
    operator_deploy_counter = Counter()       # 干员本体出场次数（仅 deploy）
    summon_deploy_counter = Counter()         # 召唤物/装置出现次数（仅 deploy）
    operator_all_counter = Counter()          # 干员出现次数（deploy+skill+retreat）
    kills_deploy_dist = Counter()             # deploy 时的 kills 分布
    kills_skill_dist = Counter()              # skill 时的 kills 分布
    location_counter = Counter()              # 部署坐标分布
    direction_counter = Counter()              # 朝向分布
    stage_operators = defaultdict(set)        # 关卡 -> 干员本体集合
    stage_summons = defaultdict(set)          # 关卡 -> 召唤物/装置集合
    stage_action_count = Counter()            # 关卡 -> 动作数
    operator_class_counter = Counter()        # 干员职业分布（从 answer 解析）
    deploy_by_kills_bucket = Counter()        # 按 kills 区间的部署数

    # 流式读取
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            total += 1
            meta = d.get("meta", {}) or {}
            action = meta.get("action", "unknown")
            operator = meta.get("operator", "")
            kills = meta.get("kills")
            location = meta.get("location")
            direction = meta.get("direction", "")
            stage = meta.get("stage", "unknown")

            action_counter[action] += 1

            # 区分干员本体和召唤物/装置
            is_real_operator = operator in operator_whitelist if operator else False

            if operator:
                operator_all_counter[operator] += 1
                if action == "deploy":
                    if is_real_operator:
                        operator_deploy_counter[operator] += 1
                    else:
                        summon_deploy_counter[operator] += 1

            if action == "deploy":
                if kills is not None:
                    kills_deploy_dist[kills] += 1
                    # kills 区间
                    bucket = (kills // 5) * 5
                    deploy_by_kills_bucket[bucket] += 1
                if location and isinstance(location, list) and len(location) == 2:
                    location_counter[(location[0], location[1])] += 1
                if direction:
                    direction_counter[direction] += 1

            if action == "skill" and kills is not None:
                kills_skill_dist[kills] += 1

            if stage and operator:
                if is_real_operator:
                    stage_operators[stage].add(operator)
                else:
                    stage_summons[stage].add(operator)
            if stage:
                stage_action_count[stage] += 1

            # 从 answer 解析干员职业（格式："干员名（职业/子职业）"）
            # 仅统计干员本体，召唤物/装置没有职业
            answer = d.get("answer", "")
            if action == "deploy" and is_real_operator and "（" in answer and "）" in answer:
                try:
                    class_part = answer.split("（")[1].split("）")[0]
                    if "/" in class_part:
                        op_class = class_part.split("/")[0]
                        operator_class_counter[op_class] += 1
                except (IndexError, ValueError):
                    pass

    # ---- 汇总 ----
    print("=" * 60)
    print("MAA 作业决策模式统计")
    print("=" * 60)
    print("总样本数: %d" % total)
    print("覆盖关卡数: %d" % len(stage_operators))
    print("干员本体数: %d（出场 %d 次）" % (len(operator_deploy_counter), sum(operator_deploy_counter.values())))
    print("召唤物/装置数: %d（出现 %d 次）" % (len(summon_deploy_counter), sum(summon_deploy_counter.values())))
    print()

    # 1. 动作类型分布
    print("--- 1. 动作类型分布 ---")
    for action, count in action_counter.most_common():
        pct = count * 100.0 / total if total else 0
        print("  %-10s %6d  (%5.1f%%)" % (action, count, pct))
    print()

    # 2. 干员本体出场频率 Top 20
    print("--- 2. 干员本体出场频率 Top 20（deploy 动作，排除召唤物/装置） ---")
    for op, count in operator_deploy_counter.most_common(20):
        print("  %-12s %4d 次" % (op, count))
    print()

    # 2b. 召唤物/装置出现频率 Top 20
    print("--- 2b. 召唤物/装置出现频率 Top 20（deploy 动作，不在 PRTS 干员白名单） ---")
    for op, count in summon_deploy_counter.most_common(20):
        print("  %-14s %4d 次" % (op, count))
    print()

    # 3. 干员职业分布
    print("--- 3. 部署干员职业分布 ---")
    for cls, count in operator_class_counter.most_common():
        pct = count * 100.0 / sum(operator_class_counter.values()) if operator_class_counter else 0
        print("  %-8s %5d  (%5.1f%%)" % (cls, count, pct))
    print()

    # 4. 部署时序（kills 区间）
    print("--- 4. 部署时序（按已击杀数区间） ---")
    for bucket in sorted(deploy_by_kills_bucket.keys()):
        count = deploy_by_kills_bucket[bucket]
        bar = "#" * min(count // 2, 50)
        print("  kills %3d-%3d: %5d  %s" % (bucket, bucket + 4, count, bar))
    print()

    # 5. 技能时机（kills 分布 Top 10）
    print("--- 5. 技能时机（按已击杀数 Top 10） ---")
    for kills, count in kills_skill_dist.most_common(10):
        print("  kills=%3d: %4d 次" % (kills, count))
    print()

    # 6. 部署位置 Top 15
    print("--- 6. 部署坐标 Top 15 ---")
    for loc, count in location_counter.most_common(15):
        print("  (%2d,%2d): %4d 次" % (loc[0], loc[1], count))
    print()

    # 7. 朝向分布
    print("--- 7. 部署朝向分布 ---")
    for d, count in direction_counter.most_common():
        pct = count * 100.0 / sum(direction_counter.values()) if direction_counter else 0
        print("  %-4s %5d  (%5.1f%%)" % (d, count, pct))
    print()

    # 8. 关卡阵容规模分布
    print("--- 8. 关卡阵容规模（干员数）分布 ---")
    team_size_counter = Counter()
    for stage, ops in stage_operators.items():
        team_size_counter[len(ops)] += 1
    for size in sorted(team_size_counter.keys()):
        count = team_size_counter[size]
        print("  %2d 干员: %4d 关" % (size, count))
    print()

    # ---- 保存 JSON ----
    stats = {
        "total_samples": total,
        "num_stages": len(stage_operators),
        "num_operators": len(operator_all_counter),
        "action_distribution": dict(action_counter),
        "operator_deploy_top50": operator_deploy_counter.most_common(50),
        "summon_deploy_top50": summon_deploy_counter.most_common(50),
        "operator_class_distribution": dict(operator_class_counter),
        "deploy_by_kills_bucket": dict(deploy_by_kills_bucket),
        "skill_by_kills_top20": kills_skill_dist.most_common(20),
        "deployment_locations_top30": location_counter.most_common(30),
        "direction_distribution": dict(direction_counter),
        "team_size_distribution": dict(team_size_counter),
        "stage_top20_by_actions": stage_action_count.most_common(20),
        "operator_whitelist_size": len(operator_whitelist),
        "num_real_operators": len(operator_deploy_counter),
        "num_summons": len(summon_deploy_counter),
        "time_field_available": False,  # meta 中无 upload_time/publish_time，无法按时间分组
    }
    out_path = os.path.join(OUTPUT_DIR, "stats.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("统计结果已保存: %s" % out_path)


if __name__ == "__main__":
    main()
