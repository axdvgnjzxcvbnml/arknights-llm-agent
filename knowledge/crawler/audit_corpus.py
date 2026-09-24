"""语料审计（CPU，不依赖 requests/bs4）：对已爬取的 PRTS JSON 做字段完整性检查。

产出 JSON 报告：按实体类型统计缺字段/空字段/异常数量，并列出抽样问题样本。
审计失败（failures>0）时以退出码 1 退出，供脚本/CI 使用。
"""

import argparse
import glob
import json
import os

__all__ = ["audit_operators", "audit_enemies", "audit_stages", "audit_corpus", "main"]

REQUIRED_OPERATOR_FIELDS = ["name", "rarity", "class", "trait", "skills"]
REQUIRED_ENEMY_FIELDS = ["name", "stats"]
REQUIRED_STAGE_FIELDS = ["name", "code", "normal"]


def _iter_json_files(root, prefix):
    return sorted(glob.glob(os.path.join(root, prefix, "*.json")))


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _missing_keys(obj, keys):
    return [k for k in keys if not obj.get(k)]


def _audit_one(obj, required):
    problems = []
    for k in _missing_keys(obj, required):
        problems.append("缺字段:%s" % k)
    if not isinstance(obj.get("skills"), list) if "skills" in required else False:
        problems.append("skills非列表")
    return problems


def audit_operators(root):
    # type: (str) -> dict
    files = _iter_json_files(root, "operators")
    bad, samples = [], []
    total_skills = 0
    for p in files:
        try:
            d = _load(p)
        except ValueError as e:
            bad.append("%s JSON解析失败:%s" % (os.path.basename(p), e))
            continue
        problems = _audit_one(d, REQUIRED_OPERATOR_FIELDS)
        skills = d.get("skills") or []
        total_skills += len(skills)
        if problems:
            bad.append("%s: %s" % (d.get("name", os.path.basename(p)), ";".join(problems)))
            if len(samples) < 10:
                samples.append({"file": os.path.basename(p), "problems": problems})
    return {"type": "operators", "count": len(files), "problems": len(bad),
            "total_skills": total_skills, "bad": bad[:50], "samples": samples}


def audit_enemies(root):
    # type: (str) -> dict
    files = _iter_json_files(root, "enemies")
    bad, samples = [], []
    for p in files:
        try:
            d = _load(p)
        except ValueError as e:
            bad.append("%s JSON解析失败:%s" % (os.path.basename(p), e))
            continue
        problems = []
        for k in REQUIRED_ENEMY_FIELDS:
            if not d.get(k):
                problems.append("缺字段:%s" % k)
        stats = d.get("stats") or []
        if stats and not all(isinstance(s, dict) and s.get("level") is not None for s in stats):
            problems.append("stats缺level")
        if problems:
            bad.append("%s: %s" % (d.get("name", os.path.basename(p)), ";".join(problems)))
            if len(samples) < 10:
                samples.append({"file": os.path.basename(p), "problems": problems})
    return {"type": "enemies", "count": len(files), "problems": len(bad),
            "bad": bad[:50], "samples": samples}


def audit_stages(root):
    # type: (str) -> dict
    files = _iter_json_files(root, "stages")
    bad, samples = [], []
    no_code = []
    for p in files:
        try:
            d = _load(p)
        except ValueError as e:
            bad.append("%s JSON解析失败:%s" % (os.path.basename(p), e))
            continue
        problems = _audit_one(d, REQUIRED_STAGE_FIELDS)
        if not d.get("code"):
            no_code.append(os.path.basename(p))
            problems.append("缺code")
        enemies = d.get("enemies") or []
        if enemies and not isinstance(enemies, list):
            problems.append("enemies非列表")
        if problems:
            bad.append("%s: %s" % (d.get("name", os.path.basename(p)), ";".join(problems)))
            if len(samples) < 10:
                samples.append({"file": os.path.basename(p), "problems": problems})
    return {"type": "stages", "count": len(files), "problems": len(bad),
            "no_code_count": len(no_code), "no_code": no_code[:20],
            "bad": bad[:50], "samples": samples}


def audit_corpus(root):
    # type: (str) -> dict
    reports = [audit_operators(root), audit_enemies(root), audit_stages(root)]
    total = sum(r["count"] for r in reports)
    problems = sum(r["problems"] for r in reports)
    return {"root": root, "total": total, "problems": problems,
            "reports": reports, "ok": problems == 0}


def main(argv=None):
    ap = argparse.ArgumentParser(description="PRTS 语料审计（离线）")
    ap.add_argument("--root", default="data/prts_raw")
    ap.add_argument("--out", default="data/prts_raw/audit_report.json")
    args = ap.parse_args(argv)
    report = audit_corpus(args.root)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("审计：%d 个实体，%d 个问题 -> %s" % (report["total"], report["problems"], args.out))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
