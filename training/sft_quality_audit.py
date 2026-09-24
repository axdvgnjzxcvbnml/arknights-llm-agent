"""SFT 数据质量审计（CPU，离线）。

对 sft_data_prep 产出的 JSONL 做机器可判的质量检查：
- schema/格式（question/answer/meta、动作头、理由段、evidence 标签、坐标元组、朝向）
- 完全重复与近重复（同关/同动作/同干员/同击杀/同费用/同坐标朝向，不同[已部署]前缀除外）
- 长度（question/answer 字符数）
- 抽样人工抽查清单输出（seed 固定，可复现）

输出：{total, problems, dup_exact, dup_near, len_min/max/mean, samples}；
problems>0 时退出码 1。
"""

import argparse
import json
import random
import re

__all__ = ["audit_file", "main"]

ACTION_HEAD = re.compile(r"^(deploy|skill|retreat) ")
REASON_RE = re.compile(r"理由：(.+)$")
EVIDENCE_TAGS = ("fact", "inferred", "retrieved")
FACING = ("上", "下", "左", "右")


def _check_one(obj):
    problems = []
    q = obj.get("question")
    a = obj.get("answer")
    meta = obj.get("meta") or {}
    if not isinstance(q, str) or not q:
        problems.append("question 缺失/为空")
    elif not q.startswith("[关卡]"):
        problems.append("question 不以 [关卡] 开头")
    if not isinstance(a, str) or not a:
        problems.append("answer 缺失/为空")
    else:
        if not ACTION_HEAD.match(a):
            problems.append("answer 动作头非法: %r" % a[:20])
        if "理由：" not in a:
            problems.append("answer 缺理由段")
        if "inferred" not in a and "fact" not in a:
            problems.append("answer 缺 evidence 标注")
    m_action = meta.get("action")
    if m_action and ACTION_HEAD.match(a or "") and not a.startswith(m_action + " "):
        problems.append("meta.action(%s) 与 answer 动作头不一致" % m_action)
    if m_action == "deploy":
        coord = meta.get("coords")
        if coord is not None:
            if not (isinstance(coord, (list, tuple)) and len(coord) == 2):
                problems.append("deploy coords 非二元组: %r" % (coord,))
        facing = meta.get("facing")
        if facing and facing not in FACING:
            problems.append("朝向非法: %r" % facing)
    return problems


def _near_key(obj):
    m = obj.get("meta") or {}
    return (m.get("stage"), m.get("action"), m.get("operator"),
            m.get("kills"), m.get("cost"), m.get("coords"), m.get("facing"))


def audit_file(path, n=50, seed=42):
    # type: (str, int, int) -> dict
    total = problems = 0
    dup_exact = {}
    dup_near = {}
    lens_q, lens_a = [], []
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            total += 1
            lines.append(obj)
            q = obj.get("question") or ""
            a = obj.get("answer") or ""
            lens_q.append(len(q))
            lens_a.append(len(a))
            key = (q, a)
            if key in dup_exact:
                dup_exact[key] += 1
            else:
                dup_exact[key] = 1
            nk = _near_key(obj)
            dup_near[nk] = dup_near.get(nk, 0) + 1
            problems += len(_check_one(obj))
    rng = random.Random(seed)
    sample = rng.sample(lines, min(n, len(lines)))
    return {
        "file": path, "total": total, "problems": problems,
        "dup_exact_groups": sum(1 for v in dup_exact.values() if v > 1),
        "dup_near_groups": sum(1 for v in dup_near.values() if v > 1),
        "dup_near_rows": sum(v for v in dup_near.values() if v > 1),
        "q_len": {"min": min(lens_q) if lens_q else 0, "max": max(lens_q) if lens_q else 0,
                  "mean": round(sum(lens_q) / len(lens_q), 1) if lens_q else 0},
        "a_len": {"min": min(lens_a) if lens_a else 0, "max": max(lens_a) if lens_a else 0,
                  "mean": round(sum(lens_a) / len(lens_a), 1) if lens_a else 0},
        "samples": sample,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT JSONL 质量审计")
    ap.add_argument("--file", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", default=None, help="审计报告输出路径（默认 stdout）")
    args = ap.parse_args(argv)
    result = audit_file(args.file, n=args.n)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("审计完成：%d 条，%d 个问题 -> %s" % (result["total"], result["problems"], args.out))
    else:
        print(text)
    return 0 if result["problems"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
