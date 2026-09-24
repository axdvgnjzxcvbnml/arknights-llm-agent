# -*- coding: utf-8 -*-
"""PRTS 全量语料质量审计（纯标准库）。

对 data/prts_raw/{operators,enemies,stages} 做：
- 文件/JSON 可解析率；
- 结构完整性与异常分类（区分“解析失败”与“页面本身数据稀疏”，不把二者混为一谈）；
- 页面标题 vs 内部名称一致性（异格形态如 阿米娅(近卫) 是不同页面，属正常，不算冲突）；
- 关键字段分布（干员星级/技能数、敌人 level 数、关卡敌情数）。
输出 JSON 报告到 data/prts_raw/corpus_audit_report.json（gitignored）并打印摘要。

用法：python -m knowledge.crawler.audit_corpus [--root data/prts_raw]
"""
import argparse
import collections
import glob
import json
import os


def _load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def audit_operators(root):
    files = sorted(glob.glob(os.path.join(root, "operators", "*.json")))
    r = {"files": len(files), "json_invalid": [], "missing_name": [], "missing_meta": [],
         "no_skills": [], "skill_missing_name": [], "no_trait": [],
         "title_name_mismatch": [], "star_dist": {}, "n_skills_dist": {}}
    star = collections.Counter()
    nsk = collections.Counter()
    for p in files:
        page = os.path.splitext(os.path.basename(p))[0]
        try:
            d = _load(p)
        except ValueError:
            r["json_invalid"].append(page); continue
        meta = d.get("meta") or {}
        name = d.get("name") or meta.get("name")
        if not name:
            r["missing_name"].append(page)
        if not meta:
            r["missing_meta"].append(page)
        skills = d.get("skills") or []
        if not skills:
            r["no_skills"].append(page)
        for s in skills:
            if not (s or {}).get("name"):
                r["skill_missing_name"].append(page); break
        if not d.get("trait"):
            r["no_trait"].append(page)
        # 标题与内部名不一致：多为异格/别名，记录供人工抽查，不判错
        if name and page != name:
            r["title_name_mismatch"].append({"page": page, "name": name})
        star[str(meta.get("star"))] += 1
        nsk[str(len(skills))] += 1
    r["star_dist"] = dict(sorted(star.items()))
    r["n_skills_dist"] = dict(sorted(nsk.items(), key=lambda x: int(x[0])))
    return r


def audit_enemies(root):
    files = sorted(glob.glob(os.path.join(root, "enemies", "*.json")))
    r = {"files": len(files), "json_invalid": [], "missing_name": [], "no_levels": [],
         "level_missing_data": [], "level_missing_name": [],
         "n_levels_dist": {}, "multi_level_fraction": None}
    nl = collections.Counter()
    for p in files:
        page = os.path.splitext(os.path.basename(p))[0]
        try:
            d = _load(p)
        except ValueError:
            r["json_invalid"].append(page); continue
        if not d.get("name"):
            r["missing_name"].append(page)
        levels = d.get("levels") or []
        if not levels:
            r["no_levels"].append(page); nl["0"] += 1; continue
        bad_data = bad_name = False
        for lv in levels:
            data = (lv or {}).get("data") if isinstance(lv, dict) else None
            if not isinstance(data, dict) or not data:
                bad_data = True
            elif not (data.get("名称") or data.get("name")):
                bad_name = True
        if bad_data:
            r["level_missing_data"].append(page)
        if bad_name:
            r["level_missing_name"].append(page)
        nl[str(len(levels))] += 1
    r["n_levels_dist"] = dict(sorted(nl.items(), key=lambda x: int(x[0])))
    multi = sum(v for k, v in nl.items() if int(k) >= 2)
    r["multi_level_fraction"] = round(multi / float(len(files)), 4) if files else None
    return r


def audit_stages(root):
    files = sorted(glob.glob(os.path.join(root, "stages", "*.json")))
    r = {"files": len(files), "json_invalid": [], "missing_code": [], "no_enemies": [],
         "enemy_missing_name": [], "n_enemies_dist": {},
         "has_raid": 0, "code_prefix_top": {}}
    ne = collections.Counter(); pref = collections.Counter()
    for p in files:
        page = os.path.splitext(os.path.basename(p))[0]
        try:
            d = _load(p)
        except ValueError:
            r["json_invalid"].append(page); continue
        code = d.get("code")
        if not code:
            r["missing_code"].append(page)
        if d.get("raid"):
            r["has_raid"] += 1
        enemies = d.get("enemies") or []
        if not enemies:
            r["no_enemies"].append(page)
        for e in enemies:
            if not (e or {}).get("名称"):
                r["enemy_missing_name"].append(page); break
        ne[str(len(enemies))] += 1
        if code:
            pref[str(code).split("-")[0]] += 1
    r["n_enemies_dist"] = dict(sorted(ne.items(), key=lambda x: int(x[0])))
    r["code_prefix_top"] = dict(pref.most_common(12))
    return r


def summarize(report):
    for kind in ("operators", "enemies", "stages"):
        r = report[kind]
        bad = {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()
               if (k.endswith("invalid") or k.startswith("missing") or k.startswith("no_")
                   or k.endswith("missing_data") or k.endswith("missing_name"))}
        hard = {k: v for k, v in bad.items() if v and k != "title_name_mismatch"}
        print("== %s：文件 %d，结构异常计数 %s" % (kind, r["files"], hard or "无"))
    inv = sum(len(report[k].get("json_invalid", [])) for k in report)
    print("JSON 解析失败总数：%d" % inv)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/prts_raw")
    args = ap.parse_args(argv)
    report = {"operators": audit_operators(args.root),
              "enemies": audit_enemies(args.root),
              "stages": audit_stages(args.root)}
    summarize(report)
    out = os.path.join(args.root, "corpus_audit_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("报告已写入 %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
