"""SFT 训练数据质量抽查（CPU 侧真实实现，纯标准库）。

输入 sft_data_prep 产出的 JSONL（默认 configs/training.yaml 的 sft.train_file），
做四类机器检查并随机抽 N 条导出人工可读样本：

  1. 结构/schema：question/answer/meta 是否齐全、类型正确、非空。
  2. answer 与 meta 一致性：动作头(deploy/skill/retreat)、干员名、坐标/朝向、理由段、
     inferred 免责注记是否齐全且自洽。
  3. evidence 分级合法性：只允许 fact:maa_job / fact:prts / inferred:timeline_reconstructed。
  4. 重复：完全相同(question,answer)；同关同动作同干员同(击杀,费用,坐标,朝向)的近重复。

机器只能查“格式与自洽性”，不能判定决策优劣；近重复与“理由是否合理”需结合人工抽读。
报告写 JSON（供统计）、抽读样本写 Markdown（供人工核对），均落在 gitignore 的数据目录。

用法：
  python -m training.sft_quality_audit                 # 默认审 train
  python -m training.sft_quality_audit --file data/sft_data/sft_eval.jsonl --n 50
"""

import argparse
import collections
import json
import os
import random

from .config import load_training_config

VALID_EVIDENCE = {
    "fact:maa_job", "fact:prts", "inferred:timeline_reconstructed",
}
ACTION_HEADS = ("deploy", "skill", "retreat")
INFERRED_NOTE = "理由由作业时间轴反推 inferred"

REQUIRED_META = [
    "stage", "source_job", "action", "action_raw", "kills",
    "operator", "location", "direction",
    "prts_stage_available", "prts_operator_available", "evidence",
]


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            rows.append((i, json.loads(line)))
    return rows


def _check_one(rec):
    """返回该样本的问题标签列表（空列表=机器检查通过）。"""
    issues = []

    if set(rec.keys()) < {"question", "answer", "meta"}:
        issues.append("schema: 缺少 question/answer/meta 顶层字段")
        return issues  # 无法继续细查
    q, a, meta = rec.get("question"), rec.get("answer"), rec.get("meta")
    if not isinstance(q, str) or not q.strip():
        issues.append("question: 为空或非字符串")
    elif not q.lstrip().startswith("[关卡]"):
        issues.append("question: 未以 [关卡] 开头")
    elif len(q.strip()) < 10:
        issues.append("question: 过短(<10字)")

    if not isinstance(a, str) or not a.strip():
        issues.append("answer: 为空或非字符串")
    else:
        head = a.lstrip().split(" ", 1)[0]
        if head not in ACTION_HEADS:
            issues.append("answer: 动作头非法(%r)" % head)
        if "理由：" not in a:
            issues.append("answer: 缺少“理由：”段")
        if INFERRED_NOTE not in a:
            issues.append("answer: 缺少 inferred 反推注记")
        # 理由至少 1 条编号项
        if "\n1)" not in a:
            issues.append("answer: 缺少编号理由项")

    if not isinstance(meta, dict):
        issues.append("meta: 非对象")
        return issues
    for k in REQUIRED_META:
        if k not in meta:
            issues.append("meta: 缺字段 %s" % k)
    action = meta.get("action")
    if action not in ACTION_HEADS:
        issues.append("meta.action: 非法(%r)" % action)
    elif isinstance(a, str) and a.lstrip().split(" ", 1)[0] != action:
        issues.append("一致性: answer 动作头与 meta.action 不一致")

    # deploy：干员需朝向（上/下/左/右）；障碍物/装置/部分召唤物无朝向（direction=None 合法）
    if action == "deploy":
        if not meta.get("operator"):
            issues.append("deploy: 缺干员名")
        loc = meta.get("location")
        if not (isinstance(loc, (list, tuple)) and len(loc) == 2):
            issues.append("deploy: 坐标非法")
        d = meta.get("direction")
        if d is not None and d not in ("上", "下", "左", "右"):
            issues.append("deploy: 朝向非法(非空且非四向)")
        if isinstance(a, str) and meta.get("operator") and meta["operator"] not in a:
            issues.append("deploy: answer 未包含干员名")
        if isinstance(a, str) and d is None and "facing" in a:
            issues.append("deploy: 无朝向放置物却输出了 facing")
    if action == "skill" and not meta.get("operator"):
        issues.append("skill: 缺干员名")
    if action == "retreat":
        loc = meta.get("location")
        if not meta.get("operator") and not (isinstance(loc, (list, tuple)) and len(loc) == 2):
            issues.append("retreat: 干员名与格子坐标都缺失")
        if isinstance(a, str) and meta.get("operator") and meta["operator"] not in a:
            issues.append("retreat: answer 未包含被撤退干员名")

    ev = meta.get("evidence")
    if not isinstance(ev, dict) or not ev:
        issues.append("evidence: 为空或非对象")
    else:
        for k, v in ev.items():
            if v not in VALID_EVIDENCE:
                issues.append("evidence: 非法标签 %s=%r" % (k, v))
        if ev.get("action") != "fact:maa_job":
            issues.append("evidence: 动作未标 fact:maa_job")
        if ev.get("rationale") != "inferred:timeline_reconstructed":
            issues.append("evidence: 理由未标 inferred:timeline_reconstructed")
    return issues


def audit(rows):
    problems = collections.Counter()
    problem_examples = collections.defaultdict(list)
    exact_seen = {}
    near_key = collections.Counter()
    n = len(rows)
    action_dist = collections.Counter()
    qlens, alens = [], []

    for line_no, rec in rows:
        for tag in _check_one(rec):
            problems[tag] += 1
            if len(problem_examples[tag]) < 5:
                problem_examples[tag].append({"line": line_no,
                                              "stage": (rec.get("meta") or {}).get("stage"),
                                              "operator": (rec.get("meta") or {}).get("operator")})
        meta = rec.get("meta") or {}
        action_dist[meta.get("action")] += 1
        qlens.append(len(rec.get("question") or ""))
        alens.append(len(rec.get("answer") or ""))

        sig_exact = ((rec.get("question") or "").strip(), (rec.get("answer") or "").strip())
        exact_seen.setdefault(sig_exact, []).append(line_no)
        sig_near = (meta.get("stage"), meta.get("action"), meta.get("operator"),
                    meta.get("kills"), json.dumps(meta.get("cost"), ensure_ascii=False),
                    json.dumps(meta.get("location"), ensure_ascii=False),
                    meta.get("direction"))
        near_key[sig_near] += 1

    exact_dup_groups = [lines for lines in exact_seen.values() if len(lines) > 1]
    near_dup_groups = {  # 同关同动作同干员同上下文出现多次（多为多份作业撞车，记录人工判断）
        "group_count": sum(1 for c in near_key.values() if c > 1),
        "extra_rows": sum(c - 1 for c in near_key.values() if c > 1),
    }

    def _pct(x):
        return round(100.0 * x / n, 3) if n else 0.0

    return {
        "n": n,
        "action_dist": dict(action_dist),
        "question_len": {"min": min(qlens), "mean": round(sum(qlens) / n, 1),
                         "max": max(qlens)},
        "answer_len": {"min": min(alens), "mean": round(sum(alens) / n, 1),
                       "max": max(alens)},
        "rows_with_any_issue": sum(1 for _ln, rec in rows if _check_one(rec)),
        "issue_rate_pct": _pct(sum(1 for _ln, rec in rows if _check_one(rec))),
        "issues": dict(problems),
        "issue_examples": dict(problem_examples),
        "exact_duplicate_groups": len(exact_dup_groups),
        "exact_duplicate_extra_rows": sum(len(g) - 1 for g in exact_dup_groups),
        "near_duplicate": near_dup_groups,
    }


def dump_samples(rows, n, seed, out_md):
    rng = random.Random(seed)
    pick = sorted(rng.sample(range(len(rows)), min(n, len(rows))))
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("# SFT train 人工抽读样本（n=%d, seed=%d）\n\n" % (n, seed))
        f.write("> 机器已做格式/自洽检查；本文件用于人工判断“理由是否合理、是否有重复/怪句”。\n\n")
        for j, idx in enumerate(pick, 1):
            _ln, rec = rows[idx]
            m = rec.get("meta") or {}
            ev = m.get("evidence") or {}
            f.write("---\n\n## 样本 %d（源行号 %s）\n\n" % (j, _ln))
            f.write("- 关卡：`%s` ｜ 作业：%s ｜ 动作：**%s** ｜ 干员：%s\n"
                    % (m.get("stage"), m.get("source_job"), m.get("action"),
                       m.get("operator")))
            f.write("- kills=%s cost=%s loc=%s 朝=%s\n"
                    % (m.get("kills"), m.get("cost"), m.get("location"),
                       m.get("direction")))
            f.write("- evidence：action=`%s` rationale=`%s` operator=`%s`\n"
                    % (ev.get("action"), ev.get("rationale"), ev.get("operator")))
            f.write("\n**QUESTION**\n\n```\n%s\n```\n\n" % rec.get("question"))
            f.write("**ANSWER**\n\n```\n%s\n```\n\n" % rec.get("answer"))
    return [rows[i][0] for i in pick]


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT 训练数据质量抽查")
    ap.add_argument("--config", default=None)
    ap.add_argument("--file", default=None, help="待审 JSONL（默认 config sft.train_file）")
    ap.add_argument("--n", type=int, default=50, help="人工抽读条数")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    cfg = load_training_config(args.config)
    sft_cfg = cfg.get("sft", {})
    dp_cfg = cfg.get("data_prep", {})
    data_dir = args.out_dir or sft_cfg.get("data_dir") or dp_cfg.get("out_dir", "data/sft_data")
    if args.file:
        path = args.file
    else:
        path = os.path.join(data_dir, sft_cfg.get("train_file", "sft_train.jsonl"))
    if not os.path.exists(path):
        raise SystemExit("[audit] 找不到 %s；请先运行 sft_data_prep --split-by-stage" % path)

    rows = load_jsonl(path)
    report = audit(rows)
    tag = os.path.splitext(os.path.basename(path))[0]
    report_path = os.path.join(data_dir, "sft_quality_report_%s.json" % tag)
    sample_path = os.path.join(data_dir, "sft_quality_samples_%s.md" % tag)
    sampled_lines = dump_samples(rows, args.n, args.seed, sample_path)
    report["audited_file"] = path
    report["sample_n"] = min(args.n, len(rows))
    report["sample_seed"] = args.seed
    report["sample_source_lines"] = sampled_lines
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("[audit] 文件 %s" % path)
    print("[audit] 样本 %d 条，问题样本 %d 条（%.3f%%）"
          % (report["n"], report["rows_with_any_issue"], report["issue_rate_pct"]))
    print("[audit] 问题分类：%s" % (report["issues"] or "无"))
    print("[audit] 完全重复组 %d（多余 %d 行）；近重复组 %d（多余 %d 行）"
          % (report["exact_duplicate_groups"], report["exact_duplicate_extra_rows"],
             report["near_duplicate"]["group_count"],
             report["near_duplicate"]["extra_rows"]))
    print("[audit] 报告 -> %s\n[audit] 抽读样本 -> %s" % (report_path, sample_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
